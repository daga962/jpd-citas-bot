# Configuración del bot de citas

## 1. Crear cuenta en GitHub
- Ir a github.com → Sign up
- Usar dgarretano@gmail.com

## 2. Crear repositorio
- New repository → nombre: `jpd-citas-bot`
- Privado (Private)
- Sin README ni .gitignore

## 3. Subir el código (hacer una sola vez)
Daniel le pasa a Lucas o lo hace desde terminal:
```bash
cd /opt/JPD/icita
git init
git add .
git commit -m "Bot citas iCITA"
git remote add origin https://github.com/USUARIO/jpd-citas-bot.git
git push -u origin main
```

## 4. Añadir los Secrets en GitHub
Settings → Secrets and variables → Actions → New repository secret

Secrets necesarios:
- TELEGRAM_BOT_TOKEN = 8573238582:AAFLqmdanaAPHL4Non8lWYt7NsGPQNXuxwc
- TELEGRAM_CHAT_ID   = 8533836941
- JULIETA_PFX_B64   = (ver abajo cómo obtenerlo)
- JULIETA_PFX_PWD   = 123456
- DANIEL_PFX_B64    = (ver abajo)
- DANIEL_PFX_PWD    = despacho2017
- DEFAULT_NIE       = (NIE del primer cliente a vigilar)
- DEFAULT_NOMBRE    = (nombre del cliente)
- DEFAULT_PAIS      = VENEZUELA
- DEFAULT_TEL       = 610965644
- DEFAULT_EMAIL     = info@jpdabogados.com

## Cómo convertir PFX a base64
Desde el servidor:
```bash
base64 -w0 /opt/JPD/certs/julieta.pfx
base64 -w0 /opt/JPD/certs/daniel.pfx
```
Copiar el resultado en el Secret correspondiente.
