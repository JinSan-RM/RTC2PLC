# RTC2PLC: Camera-PLC Integration System

This project integrates a real-time camera classification system (Breeze Runtime) with a Programmable Logic Controller (PLC) to automate plastic material sorting based on camera-detected classifications.

## Overview

The **RTC2PLC** system captures images of plastic materials (e.g., PET, PVC, HDPE) using a camera, processes classifications via Breeze Runtime, and sends corresponding signals to a PLC for automated actions. The system uses TCP socket communication to handle camera events and control PLC operations.

### Key Components
- **Camera System**: Captures images of plastic materials.
- **Breeze Runtime**: Classifies materials and sends predictions via TCP sockets.
- **Specim2PLC Script**: Processes camera events, maps classifications to PLC actions, and communicates with the PLC.
- **PLC Controller**: Sends signals to the PLC hardware to trigger physical actions (e.g., sorting).

## Setup Instructions

### Prerequisites
- Python 3.x
- Required Python packages (install via `pip install -r requirements.txt`):
  - `pyautogui`
  - `psutil`
  - `tkinter`
- Breeze Runtime installed with the workflow file at `C:/Users/withwe/breeze/Data/Runtime/Plastic_Classification_1.xml`.
- PLC hardware configured at `192.168.250.120:2004`.
- Breeze Runtime server running at `192.168.1.185` with open ports:
  - 2000 (Commands)
  - 2500 (Events)
  - 3000 (Data Stream)

### Installation
1. Clone the repository or copy the project files.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Verify network settings:
   - Ensure the PLC is accessible at `192.168.250.120:2004`.
   - Confirm Breeze Runtime is running at `192.168.1.185` with ports 2000, 2500, and 3000 open.
4. Check the workflow path in `conf.py`:
   ```python
   WORKFLOW_PATH = "C:/Users/withwe/breeze/Data/Runtime/Plastic_Classification_1.xml"
   ```

### Running the System
1. Start the main script:
   ```bash
   python Specim2PLC.py
   ```
2. Alternatively, use the GUI test tool:
   ```bash
   python app.py
   ```
3. For the web interface (if used):
   ```bash
   set FLASK_APP=src/web/server.py
   flask run --host=0.0.0.0 --port=5000
   ```

## System Workflow

1. **Camera Initialization**:
   - The script initializes the camera and loads the Breeze workflow.
   - Commands are sent via TCP (port 2000) to start predictions.

2. **Event Processing**:
   - Camera events are received on port 2500.
   - Events are parsed as JSON, extracting classification (e.g., "PET Bottle") and details (e.g., start/end line, timestamp).
   - Classifications are mapped to plastic types using `CLASS_MAPPING` and `PLASTIC_MAPPING` (defined in `conf.py`).

3. **PLC Communication**:
   - Valid classifications (e.g., PET, PVC) are mapped to PLC actions:
     - **3-second group**: PET, HDPE (Data: 0x0101, Value: 257)
     - **5-second group**: PVC, LDPE (Data: 0x0102, Value: 258)
     - **7-second group**: PP, PS (Data: 0x0111, Value: 273)
   - The system writes the class ID to `D00000` (or `D00300`) and sets the `M300` bit to trigger PLC actions.
   - Communication uses TCP sockets to the PLC at `192.168.250.120:2004`.

4. **Error Handling**:
   - The system retries failed PLC writes up to 3 times with a 0.5-second delay.
   - If Breeze or PLC connections fail, the system attempts reconnection.

## System Architecture

```
[Camera System] <--> [Breeze Runtime]
        | (TCP: 192.168.1.185:2000, 2500, 3000)
        v
[Specim2PLC.py]
        | (Command Client, Event Listener, Data Stream Listener)
        v
[PLC Controller] <--> [PLC Hardware]
        | (TCP: 192.168.250.120:2004)
```

- **Command Client**: Sends initialization and prediction commands to Breeze Runtime.
- **Event Listener**: Processes classification events and maps them to PLC actions.
- **Data Stream Listener**: Handles real-time frame metadata.
- **PLC Controller**: Sends material-specific signals to the PLC.

## Configuration

Key settings are defined in `conf.py`:
- `HOST`: Camera IP (`127.0.0.1`).
- `EVENT_PORT`: Event listener port (`2500`).
- `PLC_IP`/`PLC_PORT`: PLC address (`192.168.250.120:2004`).
- `PLC_D_ADDRESS`: Default PLC data address (`D00000`).
- `PLC_M_ADDRESS`: Default PLC bit address (`M300`).
- `CLASS_MAPPING`: Maps descriptor values to classifications (e.g., `1: "PET Bottle"`).
- `PLASTIC_MAPPING`: Maps classifications to plastic types (e.g., `"PET Bottle": "PET"`).

## Notes
- The system requires the `M300` bit to be set after writing to `D00000` to complete PLC actions.
- If the PLC is unresponsive, check the initial power setting (should be ON).
- For camera issues, verify the light source and contact the support team.
- The system is configured to handle integer values (e.g., 1, 2, 3) for `D00000` or `D00300` instead of ASCII or HEX.

## Troubleshooting
- **PLC Connection Fails**: Verify the PLC IP/port and network connectivity.
- **Breeze Fails to Start**: Check the shortcut path (`C:\Users\withwe\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Prediktera\Breeze\Breeze.lnk`).
- **Camera Issues**: Ensure the workflow file path is correct and the light source is operational.
- **Contact**: For on-site issues, reach out to the PLC or camera support team (refer to Notion: [link](https://www.notion.so/1f0af8f5754b807c9d49e2fc8e253725?pvs=4)).

## Release Notes
- **2025-05-13**: Updated to use `conf.py` for configuration, modularized PLC and camera modules.