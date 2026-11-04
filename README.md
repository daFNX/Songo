# Songo

**Songo: Tu música, sin dudas.** Es una herramienta para músicos que estima el tempo de una grabación y explora patrones armónicos. El proyecto combina una interfaz Vue 3, preprocesamiento de audio en el navegador y una API Python.

La aplicación es un prototipo funcional. BPM y grabación están disponibles; acordes, tonalidad, sesiones, similitud e historial están habilitados en producción tras configurar PostgreSQL y el secreto de sesión. La detección armónica y la comparación son aproximaciones experimentales: no identifican canciones con fiabilidad ni determinan legalmente si existe plagio. El catálogo solo debe contener material con autorización documentada.

## Arquitectura

- `src/`: interfaz Vue 3 y análisis/preprocesamiento en el navegador.
- `api/`: puntos de entrada HTTP para las funciones Python de Vercel.
- `backend/`: gateway WSGI, autenticación, persistencia, análisis armónico y catálogo.
- `db/schema.sql`: DDL de PostgreSQL.
- `src/components/TipsPage.vue` y `backend/services/tips.py`: biblioteca de consejos y administración protegida por rol.
- `tests/`: pruebas Python sin necesidad de credenciales de base de datos.
- `vercel.json`: cabeceras de seguridad y límites de las funciones.

## Secciones de la aplicación

- `/#/inicio`: presentación de Songo, su propósito y un tutorial breve.
- `/#/analizador`: carga/grabación de audio, tempo, tonalidad y secuencia aproximada de acordes.
- `/#/historial`: resultados guardados, protegidos por sesión y separados por usuario.
- `/#/consejos`: biblioteca de ejercicios para músicos y productores, con filtros y búsqueda.
- `/#/admin`: administración de consejos para cuentas con rol `admin`.
- El historial permite exportar resultados como JSON, retomarlos en el analizador y borrar de forma reversible durante 10 segundos.
- Los resultados del analizador y del historial se pueden expandir para consultar acordes con tiempos, tonalidad, medio/doble tempo y sugerencias prácticas.
- Los consejos iniciales se cargan la primera vez que una cuenta admin abre el panel; al eliminar un consejo se marca como archivado en la base de datos.

La comparación consulta únicamente entradas autorizadas cargadas por un usuario administrador. El catálogo de producción está inicialmente vacío; no se incorporan grabaciones de terceros automáticamente.

En el flujo de audio, el navegador decodifica el archivo original y lo convierte a WAV PCM mono de 11.025 Hz. El archivo convertido, de hasta 4 MB, se envía al endpoint de análisis; el servidor valida tipo, duración, canales y frecuencia, procesa las muestras en memoria y limpia los buffers mutables al terminar. No se guarda el archivo de audio.

Las cuentas usan contraseñas Argon2id y JWT firmados en cookies `HttpOnly`, `Secure` en producción y `SameSite=Strict`, con sesiones revocables persistidas en PostgreSQL. Las rutas privadas verifican la sesión y el usuario; el historial está aislado por propietario. Los intentos de autenticación y las solicitudes de análisis/catálogo se limitan por IP; con PostgreSQL el contador se comparte entre instancias y, en desarrollo sin base, se usa un límite local al proceso. Sin PostgreSQL y `JWT_SECRET` válidos, el login y las funciones dependientes permanecen desactivados, sin sesiones de demostración.

## Requisitos

- Node.js 20 o posterior y npm.
- Python 3.12 (la versión configurada para CI y Vercel).
- PostgreSQL 13 o posterior para registro, autenticación, historial y catálogo.

## Desarrollo local

1. Instala dependencias del cliente y del servidor:

   ```powershell
   npm install
   python -m pip install -r requirements.txt
   ```

2. Copia `.env.example` a `.env` y configura PostgreSQL. Genera un valor aleatorio para `JWT_SECRET` (mínimo 32 bytes). No reutilices secretos de producción.

   ```powershell
   Copy-Item .env.example .env
   ```

3. Aplica el esquema a una base de datos de desarrollo:

   Desde PowerShell, define `DATABASE_URL` en la terminal con el mismo URI configurado en `.env` y ejecuta:

   ```powershell
   $env:DATABASE_URL = "postgresql://usuario:contraseña@host:5432/songo"
   psql "$env:DATABASE_URL" -f db\schema.sql
   ```

   Si la base ya existía, el esquema añade de forma idempotente `analysis_history.deleted_at` para habilitar el borrado reversible.

   El servidor carga `.env` en desarrollo si existe; las variables ya definidas en el entorno tienen prioridad.

4. Inicia el servidor Python y Vite en terminales separadas:

   ```powershell
   python api\analyze.py
   ```

   ```powershell
   npm run dev
   ```

   Abre la dirección local que muestra Vite. El proxy envía `/api` al servidor Python en `127.0.0.1:8000`. Para probar el análisis básico sin DB, deja `DATABASE_URL` y `JWT_SECRET` sin configurar; la API reportará las funciones de cuenta como no disponibles.

5. Ejecuta las comprobaciones:

   ```powershell
   python -m unittest discover -s tests -p "test*.py"
   npm run build
   ```

## Variables de entorno

`.env.example` documenta las variables soportadas:

| Variable | Propósito |
| --- | --- |
| `DATABASE_URL` | URI privado de PostgreSQL; tiene prioridad sobre `POSTGRES_URL`. |
| `POSTGRES_URL` | Alias de Vercel/PostgreSQL. Si el URI no puede interpretarse por caracteres reservados, la conexión decodifica sus componentes o usa `POSTGRES_HOST`, `POSTGRES_DATABASE`, `POSTGRES_USER` y `POSTGRES_PASSWORD`. |
| `DATABASE_CONNECT_TIMEOUT` | Tiempo máximo de conexión a la DB. |
| `JWT_SECRET` | Secreto aleatorio de firma, de al menos 32 bytes. |
| `JWT_ISSUER` | Emisor validado en los tokens. |
| `APP_RATE_LIMIT_SECRET` | Clave opcional estable para firmar los identificadores de límite; por defecto se deriva de otro secreto del servidor. |
| `SESSION_TTL_SECONDS` | Duración de la sesión del servidor. |
| `PASSWORD_HASH_*` | Parámetros de costo de Argon2id. |
| `SONGO_ENABLED_FEATURES` | Capacidades anunciadas: BPM, grabación, acordes, similitud e historial. |
| `SONGO_CATALOG_MAX_RESULTS` | Máximo de coincidencias mostradas. |
| `APP_ENV`, `APP_BASE_URL`, `APP_ALLOWED_ORIGINS` | Cookies seguras y validación del origen para operaciones mutables. |
| `PORT` | Puerto del servidor de desarrollo. |

No guardes `.env`, URLs de base con credenciales ni secretos en Git, capturas, logs o documentos públicos. En Vercel, configura los secretos mediante **Project Settings → Environment Variables**.

## API

| Método y ruta | Acceso | Función |
| --- | --- | --- |
| `GET /api/features` | Público | Capacidades activas, disponibilidad y estado de configuración. |
| `POST /api/analyze` | Público o sesión | Estimación de BPM; tonalidad/acordes para sesiones cuando esté habilitado. Recibe WAV mono. |
| `POST /api/auth/register` | Público, con origen validado | Registro con hash Argon2id y cookie de sesión. |
| `POST /api/auth/login` | Público, con origen validado | Inicia una sesión revocable. |
| `GET /api/auth/me` | Público | Consulta la sesión actual. |
| `POST /api/auth/logout` | Sesión opcional | Revoca la sesión y expira la cookie. |
| `GET /api/history` | Sesión requerida | Historial privado del usuario autenticado. |
| `GET /api/admin/metrics` | Rol `admin` | Conteos agregados de usuarios, sesiones activas, análisis guardados y disponibilidad configurada del motor BPM. |
| `GET /api/tips` | Público | Consejos publicados; ofrece ejemplos de referencia si la base no está configurada. |
| `POST /api/tips` | Rol `admin` | Guarda/edita o elimina consejos de la biblioteca musical. |
| `POST /api/catalog` | Rol `admin` | Incorpora una referencia solo con datos de autorización y licencia. |
| `GET /api/health` | Público | Comprobación básica del proceso. |

La semejanza compara perfiles cromáticos sencillos contra el catálogo autorizado. Una coincidencia acústica no constituye una evaluación legal de plagio. No se incluye sincronización de letras, acordes en reproductores externos ni reproducción de YouTube.

## Despliegue en Vercel

1. Importa `daFNX/Songo` en Vercel o conecta el repositorio desde el panel del proyecto. El proyecto utiliza Vite y funciones Python en `api/`; `vercel.json` establece las cabeceras HTTP de seguridad.
2. Configura las variables de producción necesarias. Para habilitar cuentas, registra primero una base PostgreSQL, aplica `db/schema.sql` y carga `DATABASE_URL` y un `JWT_SECRET` generado de forma segura en Vercel. Define `APP_BASE_URL` con el dominio canónico HTTPS y activa únicamente las capacidades que hayan sido configuradas.
3. Conserva el build de frontend predeterminado (`npm run build`) y verifica el despliegue y las funciones desde los logs de Vercel.
4. Para despliegues automáticos, comprueba en Vercel **Settings → Git** que `daFNX/Songo` esté conectado y que la rama de producción sea la deseada. Un push solo activa CI/CD si esa integración está configurada correctamente.

No habilites registro público en un entorno con datos reales sin definir una estrategia de abuso, recuperación de cuenta, privacidad y operación de la base de datos. No hay migración automática: aplica y versiona los cambios de DDL con revisión.

### Primer usuario administrador

El registro público siempre crea usuarios con rol `user`; no existe contraseña, token de elevación ni endpoint de bootstrap en producción. Para crear el primer administrador:

1. Registra la cuenta desde la aplicación y confirma que esa cuenta puede iniciar sesión.
2. Desde un equipo de confianza, configura `DATABASE_URL` (o `POSTGRES_URL`) con credenciales privilegiadas de la base de datos y ejecuta:

   ```powershell
   python scripts\bootstrap_admin.py correo@ejemplo.com
   ```

3. Revisa el correo que muestra el script y escribe literalmente `PROMOTE correo@ejemplo.com` para confirmar. El script usa una transacción y un bloqueo de PostgreSQL; falla si la cuenta no existe o si ya hay cualquier administrador.

El script no se despliega como endpoint y no crea cuentas ni contraseñas. Una vez que el primer administrador exista, no puede volver a usarse para promover otra cuenta. Guarda el acceso a la base como secreto; nunca incluyas su URI en argumentos, logs o commits.

Con el rol aplicado, cierra sesión y vuelve a entrar. Abre `/#/admin` o usa el enlace **Admin** de la navegación para consultar métricas agregadas y crear, editar, publicar, ocultar y eliminar consejos musicales. La conexión mostrada en métricas verifica la respuesta del endpoint administrativo y el estado de configuración de BPM; no mide una ejecución real de audio. Los análisis sin sesión no se guardan ni aparecen en los conteos.

## Calidad y contribuciones

La integración continua instala dependencias, compila el cliente y ejecuta las pruebas Python. Antes de abrir un cambio, corre los mismos comandos localmente y sigue las convenciones del archivo [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## Limitaciones conocidas

- BPM, tonalidad y acordes son estimaciones, no transcripciones musicales certificadas.
- La huella cromática global y la comparación coseno son experimentales y no equivalen a un fingerprint robusto de reconocimiento tipo Shazam.
- No se ha medido la precisión con un corpus representativo. Evita presentar resultados como identificación, acusación de plagio o asesoramiento legal.
- La aplicación no busca letras ni integra YouTube.
