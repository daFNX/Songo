# Contribuir a Songo

Gracias por ayudar a construir Songo. Mantén cada cambio enfocado, revisable y cubierto por pruebas.

## Preparación local

Sigue los requisitos y pasos de desarrollo del [README](./README.md). No uses cuentas ni bases de producción para ejecutar pruebas; nunca agregues `.env`, audio privado ni datos personales al repositorio.

## Antes de enviar cambios

Ejecuta las verificaciones relevantes:

```powershell
python -m unittest discover -s tests -p "test*.py"
npm run build
```

Para cambios en dependencias, actualiza el manifiesto correspondiente y documenta el motivo. Los cambios de esquema deben incluir una actualización revisable de `db/schema.sql` y explicar cómo aplicarla. No actives capacidades que todavía no estén implementadas y verificadas.

## Commits

Escribe mensajes concisos en español con un prefijo convencional:

```text
feat: añade historial privado de análisis
fix: valida la duración del audio recibido
docs: explica la configuración local de PostgreSQL
refactor: separa las rutas del gateway
test: cubre errores de WAV inválido
chore: actualiza dependencias de desarrollo
```

Usa `feat`, `fix`, `docs`, `refactor`, `test` o `chore`, según corresponda. Resume el cambio en una línea, sin punto final. Añade contexto en el cuerpo únicamente cuando una decisión técnica lo necesite.

## Seguridad, audio y datos

- Valida entradas en el servidor aunque también se validen en la interfaz.
- No registres credenciales, contraseñas, cookies, contenido de audio ni tokens.
- Usa datos de catálogo cuya autorización y licencia puedan acreditarse.
- Una similitud acústica no es un dictamen de plagio.
- No declares una función lista para producción sin pruebas y configuración explícita.
