# Bluetti Chisme ⚡

Interfaz web **local y en español** para buscar tu **BLUETTI Elite 100 V2** por Bluetooth LE, conectarte, explorar sus servicios y probar la lectura de sus datos. Python habla con el adaptador Bluetooth de la computadora; el navegador muestra la interfaz. No requiere MQTT, Home Assistant, nube ni credenciales BLUETTI.

## Qué puedes hacer

- Buscar dispositivos BLE, con candidatos BLUETTI destacados y opción de mostrar todos.
- Conectar y descubrir servicios y características GATT, aunque la telemetría no esté disponible.
- Leer características que anuncien la propiedad `read`, mostrando hexadecimal y texto.
- Intentar telemetría V2: batería, voltaje, corriente, potencias y estados disponibles.
- Ver un gráfico AC y hasta 720 lecturas en memoria (aprox. una hora con lecturas de 5 s).
- Exportar un JSON con anuncios, servicios, últimas lecturas, historial y registro.
- Probar la interfaz con un modo demo que identifica los datos simulados.

La aplicación no expone controles para cambiar salidas AC/DC ni escribir registros de configuración. El protocolo de telemetría sí escribe solicitudes de lectura y mensajes de negociación en la característica de comunicación BLE.

## Estado de compatibilidad: importante para tu Elite 100 V2

**Todavía no se ha probado esta aplicación con una Elite 100 V2 real.** Poder descubrir o conectar un equipo BLE no garantiza que su firmware acepte la negociación ni que use este mapa de registros.

El adaptador de telemetría incorpora los decodificadores del núcleo de [`j4m3z0r/bluetti-monitor`](https://github.com/j4m3z0r/bluetti-monitor), commit `72a46f1790ecc2be6c9c0d5b375e94e1506c44a0`, con licencia MIT. La conexión cifrada se delega al SDK oficial que el propietario instala localmente; no se distribuyen claves privadas ni binarios. Aquí se usa el mapa V2 (página 100), no se promete soporte verificado para la Elite 100 V2. Las lecturas se rechazan si el SOC no está entre 0 y 100; ese control no certifica que todos los demás campos estén bien interpretados.

La detección usa nombre, marcador BLUETTI/BLUETTE en datos del fabricante y servicio FF00. Cuando el cifrado es desconocido se intenta el modo cifrado, acorde con el objetivo Elite V2; puedes elegir otro modo. Si el firmware requiere una licencia o una autenticación adicional no implementada, el intento puede fallar. No se inventan lecturas: se muestra el error y se permite reconectar para explorar GATT.

### Cifrado oficial (necesario si tu firmware usa BLUETTE)

La búsqueda, conexión BLE y exploración GATT funcionan sin el SDK. Para intentar **telemetría cifrada**, el transporte integra de forma opcional la API del [módulo oficial BLUETTI](https://github.com/bluetti-official/bluetti-bluetooth-lib):

1. Obtén del proyecto oficial el binario y el wrapper `bluetti_crypt` compatibles con tu sistema, arquitectura y versión exacta de Python. El ejemplo oficial de Linux usa Python 3.12; no presupongas que un binario sirve para cualquier versión.
2. Instálalos en el `site-packages` del entorno `.venv`, siguiendo la documentación oficial. Comprueba con `.venv/bin/python -c "import bluetti_crypt"`.
3. Obtén mediante el procedimiento autorizado de BLUETTI el archivo de licencia correspondiente al **Communication Board SN** de tu equipo. Guarda ese archivo como `bluetti_device_licence.csv` en la raíz del proyecto y ejecuta la app desde allí (los scripts ya lo hacen).
4. Selecciona modo cifrado e inicia lecturas. El transporte llama a `BluettiCrypt()`, `ble_crypt_link_handler()`, `encrypt_data()` y `decrypt_data()`, de acuerdo con los ejemplos oficiales.

No se incluye ni se genera la licencia del dispositivo y no se proporcionan claves de autenticación. Estos archivos están excluidos de Git. Sin módulo o licencia, el error indica qué falta; no es una conexión cifrada lista para usar sin aprovisionamiento. La integración del SDK también está pendiente de probar con el hardware real y puede requerir ajustes según el SDK y firmware. No se utiliza la ruta de claves fijas de la biblioteca comunitaria.

## Inicio rápido en Linux Mint / Ubuntu

Necesitas Python 3.10+ y un adaptador Bluetooth LE funcionando. Instala los paquetes del sistema si faltan:

```bash
sudo apt update
sudo apt install python3-venv python3-pip bluez
sudo systemctl enable --now bluetooth
```

Descarga el proyecto y arráncalo desde la rama de desarrollo:

```bash
git clone -b feat/bluetti-explorer https://github.com/Alej0prepper/Bluetti_chisme.git
cd Bluetti_chisme
bash start.sh
```

Abre **http://127.0.0.1:8765** en el navegador de esa computadora. Tras instalar dependencias, la comunicación BLE no necesita internet. No ejecutes la aplicación con `sudo`.

Para ver la interfaz sin una estación cercana:

```bash
bash start.sh --demo
```

## Windows

Con Python 3.10+ y Bluetooth LE activado, abre PowerShell en el proyecto:

```powershell
.\start.ps1
# Para datos simulados:
.\start.ps1 -Demo
```

Alternativa manual si tu política de PowerShell no permite scripts:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m uvicorn explorer.app:app --host 127.0.0.1 --port 8765
```

## Cómo chismear con la estación real

1. Enciende la Elite 100 V2. Activa Bluetooth según sus ajustes y acerca la computadora.
2. Cierra la app BLUETTI del teléfono para evitar que ocupe la conexión.
3. Pulsa **Buscar por Bluetooth**. Si no aparece entre los candidatos, activa **Mostrar todos los dispositivos BLE**.
4. Elige el equipo y pulsa **Conectar y explorar**. El estado debe decir **BLE conectado**.
5. Revisa **Servicios Bluetooth**. Las lecturas GATT directas solo están disponibles en esta fase y si la característica permite `read`. Las características `notify` no se leen de esta forma.
6. Pulsa **Iniciar lecturas V2**. La aplicación reconecta y negocia el protocolo. La primera lectura puede tardar más de un minuto; la interfaz muestra el progreso.
7. Si funciona, aparecerán los datos y el gráfico. Si falla, reconecta para explorar GATT, prueba otro modo de cifrado o exporta el diagnóstico para ajustar el adaptador al firmware.
8. Usa **Desconectar** al terminar. `Ctrl+C` cierra el servidor y libera la conexión.

La aplicación no necesita emparejamiento manual en el menú del sistema para iniciar su intento BLE. Si el firmware solicita una autorización propia, este flujo puede no bastar.

## Si algo falla

- **No encuentra dispositivos:** comprueba `bluetoothctl show`, `rfkill list bluetooth` y que el adaptador admita BLE. Sal de la app del teléfono y acerca la estación.
- **Bluetooth bloqueado:** si `rfkill` muestra bloqueo por software, usa `sudo rfkill unblock bluetooth`; un bloqueo físico se libera en el equipo.
- **BlueZ / D-Bus no disponible:** ejecútalo directamente en Linux Mint, no dentro de un contenedor, WSL o esta sesión de ChatGPT. No necesitas desplegarlo en tu VPS: el adaptador debe estar cerca de la estación.
- **Timeout de protocolo / handshake:** puede ser una incompatibilidad de cifrado o firmware, aunque la conexión BLE básica funcione. No cambies configuraciones de energía para intentar corregirlo.
- **Se cortó la conexión:** el sondeo se detiene, se marca la última lectura como no actualizada y se puede reconectar manualmente. No hay reintentos infinitos.
- **Quedó una conexión atascada en Linux:** desconecta el equipo desde el gestor Bluetooth o con `bluetoothctl disconnect DIRECCION_MAC` y busca de nuevo.

La app escucha solo en `127.0.0.1`, valida el host y rechaza peticiones de escritura procedentes de otros orígenes web. No incluye autenticación para acceso remoto; conserva el arranque local. La exportación puede contener nombre del dispositivo, dirección BLE o identificadores: revísala antes de compartirla.

## Desarrollo y pruebas

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
BLUETTI_DEMO=1 python -m uvicorn explorer.app:app --host 127.0.0.1 --port 8765
```

- `explorer/manager.py`: búsqueda, conexión, sondeo, historial y diagnóstico.
- `explorer/app.py`: API FastAPI y servidor de interfaz.
- `explorer/static/`: interfaz sin dependencias JavaScript externas.
- `bluetti_monitor/`: transporte de solo lectura y decodificadores, sin MQTT ni claves fijas.
- `third_party/`: licencia y atribución del código de origen.
- `tests/`: API demo, anuncios, errores de conexión, limpieza, lecturas inválidas y controles de acceso.

Las pruebas con dobles y el modo demo validan el software; la validación Bluetooth con tu equipo físico sigue pendiente. Las lecturas permanecen en memoria y se pierden al cerrar el proceso salvo que las exportes.
