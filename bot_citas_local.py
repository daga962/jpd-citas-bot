#!/usr/bin/env python3
"""
Bot Citas iCITA — JPD Abogados
Ejecutar en el PC del despacho. Comprueba cada 5 minutos y avisa por Telegram.
"""
import os, sys, time, base64, tempfile, requests
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
BOT_TOKEN = "8573238582:AAFLqmdanaAPHL4Non8lWYt7NsGPQNXuxwc"
CHAT_ID   = "8533836941"

# Ruta a los certificados (ajustar si están en otro lugar)
SCRIPT_DIR = Path(__file__).parent
CERT_JULIETA = SCRIPT_DIR / "julieta.pfx"
CERT_DANIEL  = SCRIPT_DIR / "daniel.pfx"
CERT_PASSWD  = {"julieta": "123456", "daniel": "despacho2017"}

ICITA_URL = "https://icp.administracionelectronica.gob.es/icpplus/citar?p=28"

INTERVALO_MINUTOS = 5

# ── Trámites disponibles ───────────────────────────────────────────────────────
TRAMITES = {
    "huellas": ["huella", "expedición de tarjeta", "tprex"],
    "ue":      ["ciudadano de la u", "comunitario", "registro de ciudadano"],
}

# ── Cola de clientes a vigilar (añadir/quitar según necesidad) ─────────────────
# Cada entrada: (nie, nombre, pais, tramite)
CLIENTES = [
    ("Y4257335A", "VALENTINA OSORIO ANGULO", "COLOMBIA", "huellas"),
]


# ── Telegram ──────────────────────────────────────────────────────────────────
def tg(texto):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": texto}, timeout=10)
    except Exception as e:
        print(f"[Telegram ERROR] {e}")

def tg_foto(ruta, caption=""):
    try:
        with open(ruta, "rb") as f:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                          data={"chat_id": CHAT_ID, "caption": caption},
                          files={"photo": f}, timeout=20)
    except Exception as e:
        print(f"[Telegram foto ERROR] {e}")


# ── Comprobar un cliente ───────────────────────────────────────────────────────
def comprobar(nie, nombre, pais, tramite_tipo, cert="julieta"):
    pfx_path = CERT_JULIETA if cert == "julieta" else CERT_DANIEL
    if not pfx_path.exists():
        print(f"  ⚠ Certificado no encontrado: {pfx_path}")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-ES",
            viewport={"width": 1280, "height": 900},
            client_certificates=[{
                "origin": "https://sede.administracionespublicas.gob.es",
                "pfxPath": str(pfx_path),
                "passphrase": CERT_PASSWD[cert],
            }]
        )
        page = ctx.new_page()
        resultado = False

        try:
            print(f"  → Cargando iCITA...")
            page.goto(ICITA_URL, timeout=60000)
            page.wait_for_load_state("domcontentloaded", timeout=30000)

            if "403" in page.title() or "Forbidden" in page.content():
                print("  ⚠ Bloqueado (403)")
                return False

            # Esperar desafío JS (TSPD) y carga real
            try:
                page.wait_for_selector("select", timeout=20000)
            except Exception:
                pass

            # Seleccionar trámite
            tramite_sel = page.locator("select").first
            keywords = TRAMITES.get(tramite_tipo, [tramite_tipo])
            tramite_val = None
            for opt in tramite_sel.locator("option").all():
                txt = opt.inner_text().lower()
                val = opt.get_attribute("value") or ""
                if any(k in txt or k in val.lower() for k in keywords):
                    tramite_val = val
                    print(f"  → Trámite: {opt.inner_text().strip()}")
                    break

            if not tramite_val:
                print("  ⚠ Trámite no encontrado en el desplegable")
                return False

            tramite_sel.select_option(value=tramite_val)
            page.locator("input[type=submit], button[type=submit]").first.click()
            page.wait_for_load_state("networkidle", timeout=20000)

            # Esperar formulario de datos
            page.wait_for_selector(
                "input[name='idCiudadano'], input[id*='NIE'], input[id*='nie'], input[name*='nie']",
                timeout=20000
            )

            # Rellenar datos del cliente
            print(f"  → Rellenando datos: {nie} / {nombre}")
            nie_inp = page.locator("input[name='idCiudadano'], input[id*='NIE'], input[name*='nie']").first
            nie_inp.fill(nie)

            nom_inp = page.locator("input[name='desCiudadano'], input[name*='nombre'], input[id*='nombre']").first
            nom_inp.fill(nombre)

            pais_sel = page.locator("select[name*='pais'], select[id*='pais'], select[name*='nacion']").first
            if pais_sel.count():
                for opt in pais_sel.locator("option").all():
                    if pais.upper() in opt.inner_text().upper():
                        pais_sel.select_option(value=opt.get_attribute("value"))
                        break

            page.locator("input[type=submit][value*='Aceptar'], button:text-is('Aceptar')").first.click()
            page.wait_for_load_state("networkidle", timeout=20000)

            # Verificar disponibilidad
            content = page.content().lower()
            sin_cita = any(t in content for t in [
                "no hay citas", "no existen citas", "no quedan citas",
                "no hay huecos", "vuelva a intentarlo", "en este momento no"
            ])

            if sin_cita:
                print("  Sin citas disponibles.")
                return False

            # Buscar elementos de calendario/disponibilidad
            hay_citas = (
                page.locator("td.verde, td.disponible, a.cita, .cita-disponible, td[class*='disp']").count() > 0
                or page.locator("table.calendario, .tablacalendario").count() > 0
            )

            if hay_citas:
                ss = str(SCRIPT_DIR / "cita_disponible.png")
                page.screenshot(path=ss, full_page=True)
                msg = f"🎉 HAY CITAS!\n{nombre}\n{nie}\nEntra ahora: {ICITA_URL}"
                tg_foto(ss, msg)
                print(f"  ✅ CITAS ENCONTRADAS — Telegram enviado")
                resultado = True
            else:
                print("  Sin citas detectadas.")

        except PWTimeout:
            print("  Timeout cargando la página — reintentando en el próximo ciclo")
        except Exception as e:
            print(f"  Error: {e}")
        finally:
            browser.close()

    return resultado


# ── Bucle principal ────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Bot Citas iCITA — JPD Abogados")
    print(f"  Comprobando cada {INTERVALO_MINUTOS} minutos")
    print(f"  Clientes: {len(CLIENTES)}")
    print("  Ctrl+C para detener")
    print("=" * 55)

    tg(f"✅ Bot citas iniciado. Vigilando {len(CLIENTES)} cliente(s) cada {INTERVALO_MINUTOS} min.")

    while True:
        import datetime
        ahora = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"\n[{ahora}] Comprobando...")

        for nie, nombre, pais, tramite in CLIENTES:
            print(f"  Cliente: {nombre} ({nie})")
            comprobar(nie, nombre, pais, tramite, cert="julieta")

        print(f"  Siguiente comprobación en {INTERVALO_MINUTOS} min.")
        time.sleep(INTERVALO_MINUTOS * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBot detenido.")
        tg("⛔ Bot citas detenido manualmente.")
