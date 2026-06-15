#!/usr/bin/env python3
"""
Bot citas iCITA — Toma de Huellas Extranjería Madrid
Autenticación con certificado digital (Cl@ve) + reserva automática hasta paso SMS.
"""
import os, sys, json, base64, tempfile, time, requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── Configuración desde variables de entorno ──────────────────────────────────
BOT_TOKEN   = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID     = os.environ['TELEGRAM_CHAT_ID']

# Certificado a usar: 'julieta' o 'daniel'
CERT_QUIEN  = os.environ.get('CERT_QUIEN', 'julieta')
PFX_B64     = os.environ[f'{CERT_QUIEN.upper()}_PFX_B64']
PFX_PWD     = os.environ[f'{CERT_QUIEN.upper()}_PFX_PWD']

# Datos del cliente
CLIENTE_NIE     = os.environ.get('CLIENTE_NIE', 'TEST123')
CLIENTE_NOMBRE  = os.environ.get('CLIENTE_NOMBRE', 'PRUEBA BOT')
CLIENTE_PAIS    = os.environ.get('CLIENTE_PAIS', 'VENEZUELA')
CLIENTE_TEL     = os.environ.get('CLIENTE_TEL', '')
CLIENTE_EMAIL   = os.environ.get('CLIENTE_EMAIL', '')

# Tipo de trámite a buscar (palabras clave del texto del dropdown)
# 'huellas' = TIE toma de huellas | 'ue' = ciudadano UE | o texto libre
TRAMITE_TIPO    = os.environ.get('TRAMITE_TIPO', 'huellas')

# URL base
ICITA_BASE = 'https://icp.administracionelectronica.gob.es/icpplus'
ICITA_URL  = f'{ICITA_BASE}/citar?p=28'


# ── Telegram helpers ─────────────────────────────────────────────────────────
def tg(texto, modo=None):
    payload = {'chat_id': CHAT_ID, 'text': texto}
    if modo:
        payload['parse_mode'] = modo
    requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                  json=payload, timeout=10)

def tg_foto(ruta, caption=''):
    with open(ruta, 'rb') as f:
        requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto',
                      data={'chat_id': CHAT_ID, 'caption': caption},
                      files={'photo': f}, timeout=20)


# ── Función principal ────────────────────────────────────────────────────────
def run():
    # Guardar PFX en fichero temporal
    pfx_bytes = base64.b64decode(PFX_B64)
    tmp = tempfile.NamedTemporaryFile(suffix='.pfx', delete=False)
    tmp.write(pfx_bytes); tmp.close()

    resultado = False
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='es-ES',
            viewport={'width': 1280, 'height': 900},
            client_certificates=[{
                'origin': 'https://sede.administracionespublicas.gob.es',
                'pfxPath': tmp.name,
                'passphrase': PFX_PWD,
            }]
        )
        page = ctx.new_page()

        try:
            # ── Paso 1: Primero probar conectividad básica ────────────────
            print('→ Probando conectividad...')
            page.goto('https://www.google.com', timeout=15000)
            print('  Google OK')

            # ── Paso 2: Página iCITA Madrid ──────────────────────────────
            print('→ Cargando iCITA Madrid...')
            page.goto(ICITA_URL, timeout=60000)
            page.wait_for_load_state('domcontentloaded', timeout=30000)
            print(f'  Título: {page.title()!r}')
            print(f'  URL: {page.url}')
            print(f'  Contenido (500 chars): {page.content()[:500]}')

            if '403' in page.title() or 'Forbidden' in page.content():
                tg('⚠️ Bot citas: IP bloqueada por el gobierno (403). Avisar a Lucas.')
                return False

            # Esperar a que el desafío JS (TSPD) termine y cargue la página real
            try:
                page.wait_for_selector('select', timeout=20000)
            except PWTimeout:
                pass  # Puede que ya haya cargado

            # ── Paso 2: Seleccionar trámite ──────────────────────────────
            print('→ Buscando trámite de huellas...')
            tramite_sel = page.locator('select').first
            # Imprimir todos los trámites disponibles para diagnóstico
            print('  Trámites disponibles:')
            for opt in tramite_sel.locator('option').all():
                v = opt.get_attribute('value') or ''
                t = opt.inner_text().strip()
                if v: print(f'    [{v}] {t}')

            # Buscar trámite según TRAMITE_TIPO
            tipo = TRAMITE_TIPO.lower()
            TRAMITE_KEYWORDS = {
                'huellas': ['huella', 'expedición de tarjeta', 'tprex'],
                'ue':      ['ciudadano de la u', 'comunitario', 'registro de ciudadano'],
            }
            keywords = TRAMITE_KEYWORDS.get(tipo, [tipo])  # si no es un alias, buscar literal

            tramite_val = None
            for opt in tramite_sel.locator('option').all():
                txt = opt.inner_text().lower()
                val = opt.get_attribute('value') or ''
                if any(k in txt or k in val.lower() for k in keywords):
                    tramite_val = val
                    print(f'  Trámite seleccionado: [{val}] {opt.inner_text().strip()}')
                    break

            if not tramite_val:
                # Dump opciones para diagnóstico
                opts = [(o.get_attribute('value'), o.inner_text().strip())
                        for o in tramite_sel.locator('option').all() if o.get_attribute('value')]
                print('Opciones disponibles:', opts)
                tg(f'⚠️ Bot citas: no encontré el trámite de huellas.\nOpciones: {opts}')
                return False

            tramite_sel.select_option(value=tramite_val)
            page.locator('input[type=submit], button[type=submit]').first.click()
            page.wait_for_load_state('networkidle', timeout=20000)

            # ── Paso 3: Autenticación con certificado ────────────────────
            # El navegador presenta automáticamente el certificado si aparece el prompt
            # Esperamos el formulario de datos del solicitante
            print('→ Esperando formulario post-certificado...')
            try:
                page.wait_for_selector(
                    'input[name="idCiudadano"], input[id*="NIE"], input[id*="nie"], '
                    'input[name*="nie"], input[name*="NIE"]',
                    timeout=20000
                )
            except PWTimeout:
                ss = '/tmp/debug_step3.png'
                page.screenshot(path=ss)
                tg_foto(ss, '⚠️ Bot citas: no llegué al formulario. Ver captura.')
                return False

            # ── Paso 4: Rellenar datos del cliente ───────────────────────
            print(f'→ Rellenando datos: {CLIENTE_NIE} / {CLIENTE_NOMBRE}')

            nie_input = page.locator(
                'input[name="idCiudadano"], input[id*="NIE"], input[id*="nie"], input[name*="nie"]'
            ).first
            nie_input.fill(CLIENTE_NIE)

            nombre_input = page.locator(
                'input[name="desCiudadano"], input[id*="nombre"], input[name*="nombre"], '
                'input[id*="Nombre"], input[name*="Nombre"]'
            ).first
            nombre_input.fill(CLIENTE_NOMBRE)

            # País de nacionalidad
            pais_sel = page.locator(
                'select[name*="pais"], select[name*="Pais"], select[id*="pais"], '
                'select[id*="Pais"], select[name*="nacion"]'
            ).first
            if pais_sel.count():
                try:
                    pais_sel.select_option(label=CLIENTE_PAIS)
                except Exception:
                    # Buscar por texto parcial
                    for opt in pais_sel.locator('option').all():
                        if CLIENTE_PAIS.upper() in opt.inner_text().upper():
                            pais_sel.select_option(value=opt.get_attribute('value'))
                            break

            # Teléfono y email (si los hay)
            if CLIENTE_TEL:
                tel_input = page.locator('input[name*="tel"], input[id*="tel"]').first
                if tel_input.count():
                    tel_input.fill(CLIENTE_TEL)

            if CLIENTE_EMAIL:
                email_input = page.locator('input[name*="email"], input[id*="email"], input[type=email]').first
                if email_input.count():
                    email_input.fill(CLIENTE_EMAIL)

            # Aceptar
            page.locator(
                'input[type=submit][value*="Aceptar"], input[type=submit][value*="aceptar"], '
                'button:text-is("Aceptar")'
            ).first.click()
            page.wait_for_load_state('networkidle', timeout=20000)

            # ── Paso 5: Verificar si hay citas disponibles ───────────────
            print('→ Comprobando disponibilidad...')
            content = page.content()

            # Indicadores de "sin citas"
            sin_cita_texts = [
                'no hay citas disponibles',
                'no existen citas',
                'no quedan citas',
                'no hay huecos',
                'vuelva a intentarlo',
            ]
            if any(t in content.lower() for t in sin_cita_texts):
                print('Sin citas disponibles.')
                return False

            # Indicadores de disponibilidad
            citas_disponibles = page.locator(
                'td.verde, td.disponible, a.cita, .cita-disponible, '
                'td[class*="disp"], a[title*="cita"]'
            )
            hay_citas = citas_disponibles.count() > 0

            # Si el calendario cargó con días, probablemente hay citas
            if not hay_citas:
                hay_citas = bool(page.locator('table.calendario, .tablacalendario, #cal').count())

            if hay_citas:
                ss = '/tmp/cita_disponible.png'
                page.screenshot(path=ss, full_page=True)
                tg_foto(ss,
                    f'🎉 HAY CITAS DISPONIBLES!\n'
                    f'Cliente: {CLIENTE_NOMBRE}\n'
                    f'NIE: {CLIENTE_NIE}\n'
                    f'Accede ahora: {ICITA_URL}'
                )
                resultado = True
            else:
                print('No se detectaron huecos.')

        except Exception as e:
            print(f'Error inesperado: {e}')
            try:
                ss = '/tmp/error.png'
                page.screenshot(path=ss)
                tg_foto(ss, f'⚠️ Bot citas: error inesperado\n{e}')
            except Exception:
                tg(f'⚠️ Bot citas: error inesperado\n{e}')
        finally:
            os.unlink(tmp.name)
            browser.close()

    return resultado


if __name__ == '__main__':
    ok = run()
    sys.exit(0 if ok else 0)  # exit 0 siempre para no fallar el workflow
