# Project Summary

This project implements a networked embedded control system on the 
[W5500-EVB-PICO2 board](https://wiznet.io/products/evaluation-boards/w5500-evb-pico2), 
targeting real-time astrophotonic device management. It uses FreeRTOS, the pPI Pico SDK, and a 
lightweight Zyre-like messaging layer to handle:

- Incoming mKTL-based TCP commands (WHISPER)
- Asynchronous photodiode telemetry (PUB)
- Dynamic network discovery (ENTER UDP broadcast)

Key hardware devices include:
- external photodiodes (read out by an ADS1115)
- 8 MEMS optical switches (driven by a PCAL6416A GPIO expander)
- 6 variable optical attenuators (controlled by an 8-channel DAC DAC7578)
- Laser diodes controlled over RS48 and driven by Maiman electronics SF8250-ZIF14.

The code emphasizes static memory layout, task separation, clear ownership of devices, and lightweight error 
handling (no runtime exceptions). Networking is DHCP-based and automatically recovers after link loss.

All command dispatch flow through a central `executor_task`, structured for extensibility. Parsing of mKTL JSON payloads
are parsed via `nlohmann::json` internal to the `coms_task`, and keys for device control are defined cleanly in `keys.h`.

Work remains in areas like laser control integration, persistent calibration storage, and broader command coverage. 
Developers are strongly encouraged to understand the FreeRTOS task structure and device initialization flow before 
making changes.

---

## 1. Hardware Overview

The embedded system is based on the **W5500-EVB-PICO2** development board, which combines:
- A **RP2350 microcontroller** (dual Cortex-M33 cores, 264 KB SRAM, 2 MB flash)
- A **WIZnet W5500 Ethernet controller** (SPI-based TCP/IP offload)
- Integrated Ethernet PHY with RJ45 jack.

The board interfaces with several external devices:
- 2 **Photodiodes** connected via an **ADS1115 ADC** (I2C bus).
- 8 **MEMS optical switches** controlled through a **PCAL6416A GPIO expander** (I2C bus).
- 6 **Laser diode drivers** controlled via TTL level RS-485 bus.
- 6 **Variable optical attenuators**, driven via a **DAC7578 DAC** (I2C bus).
- 1 power swtich to power down the photodiodes and laser drivers (a GPIO pin)

The system uses FreeRTOS for task management and standard Pico-SDK libraries for low-level hardware interfaces.

---

## 2. Design Intent and Philosophy

The project is designed to create a **reliable, networked controller** capable of:

- Responding to **dynamic mKTL-based network commands** over TCP (router/whisper style)
- **Publishing sensor data** (photodiode voltages) asynchronously via Zyre-style PUB sockets
- **Self-discovering** on a local network using **Zyre UDP broadcast ("ENTER")**

### Key design philosophies:
- **Minimal moving parts**: minimal tasks, minimal inter-task coordination complexity.
- **Single Ownership**: Devices (photodiodes, attenuators, switches) are instantiated once, lifetime-managed explicitly.
- **Clear concurrency model**: Only genuinely asynchronous hardware polling (photodiodes) is task-separated.
- **Memory efficiency**: Avoid dynamic allocations where possible; careful use of `string_view`, fixed buffers, and compile-time constants.
- **Future resilience**: Structured around extensibility (e.g., laser diode driver support, additional sensors).
- **FreeRTOS Realism**: Pragmatic use of mutexes where needed, but prefer single-task device ownership when possible.
- **Avoid runtime exceptions**: C++ exceptions are disabled; error handling is done via return codes and checking object states.

---

## 3. Code Structure and Instructions

### High-Level Architecture:

| Area                  | Description                                                                                      |
|-----------------------|--------------------------------------------------------------------------------------------------|
| `main.cpp`            | Initializes hardware, tasks, queues, and the shared context object                               |
| `hardware_context.h`  | Defines the shared `HardwareContext` passed to tasks                                             |
| `executor_task.cpp`   | Main command dispatcher: acts on inbound mKTL commands and builds replies                        |
| `photodiode_task.cpp` | Asynchronously polls photodiode voltages and sends updates via the PUB queue                     |
| `photodiode.cpp`      | A photodiode object                                                                              |
| `maiman.cpp`          | A Maiman laser diode object                                                                      |
| `attenuator.cpp`      | An attenuator object                                                                             |
| `coms_task.cpp`       | Manages Zyre beaconing, incoming WHISPER handling, actually sending ack/replys, and outbound PUB |
| `pico_zyre.cpp`       | Provides lightweight Zyre protocol support (ENTER broadcast, WHISPER receiving, PUB sending)     |
| `mems_switching.cpp`  | Abstracts control over MEMSSwitch devices and the MEMSRouter class                               |
| `mktl_keys.h`         | Centralized mKTL key prefixes/suffixes for matching against inbound commands                     |

### Key libraries:

- **nlohmann/json**: Used for lightweight JSON parsing of inbound mKTL messages
- **Pico SDK**: Base microcontroller support
- **WIZnet ioLibrary Driver**: Raw SPI Ethernet stack for W5500
- **FreeRTOS**: Task scheduling and resource sharing

---

### Explicit Developer Instructions:

- **Review major code (`tip-pico2/*`) carefully.**  
  Each is intended to be (strongly) modular and typically owns its domain of hardware or communication.
- **The true command and control flow is in `executor_task.cpp`.**  
  New commands, hardware devices, and features must be added by expanding the dispatcher tables there. It is presently unfinished
- **Device initialization (photodiodes, attenuators, switches) happens in `main.cpp`.**  
  All shared objects are passed through `HardwareContext`.
- **Zyre network behavior (discovery and messaging) is in `pico_zyre.cpp`.**  
  See `ZyreBeacon::tick()` and `maybe_send_enter()` for dynamic IP broadcasting.
- **Message framing and unframing follows strict multipart framing rules (see `ZyreFramer::decode` and `encode`).**  
  Always validate or extend message parsing at the framer level, not inside tasks.
  The executor_task is responsible for properly packaging results into the JSON payload for a Response. This is out of scope for pico_zyre
- **Look carefully at the key naming convention in `mktl_keys.h` when matching or dispatching mKTL commands.**  
  Prefixes and suffixes are split for flexibility and clarity.
- **No C++ exceptions are permitted at runtime.**  
  Any new library usage or parsing must use fail-safe, non-throwing patterns.
- **Networking is dynamic with DHCP.**  
  If the Ethernet link is dropped and recovered, DHCP automatically restarts.

If reviewing with an AI or static analysis tool:
- Ask it to **trace main task interactions** (command-in queue, response-out queue, pub-out queue)
- Review each task's control loop separately for sleeping and blocking behavior
- Be aware that socket numbers and uses (e.g., WHISPER sockets) are **hardwired constants** in `pico_zyre`
- Recognize that **memory layout is static**; dynamic malloc is avoided wherever possible.

---

## 4. Outstanding Tasks and Future Work

| Area                               | Description                                                                                                                                                                                                                        |
|------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Laser Diode Driver Integration** | Preliminary work only. status() and config() commands are missing.                                                                                                                                                                 |
| **Full Command Dispatch Coverage** | Only a subset of mKTL command space is wired. Need to extend `executor_task` for things like system status, laser commands, and calibration writes, persistence of settings to flash, and packaging of results into response JSON. |
| **EEPROM / Flash Storage**         | Settings (e.g., calibration curves) are not persisted across reboots. This needs to be added.                                                                                                                                      |
| **SNTP Integration**               | SNTP integration could offer powerful debugging capabilities and should be added.                                                                                                                                                  |
| **Formal Testing**                 | Unit tests for command parsing, error paths, and hardware failure modes are recommended. No automated tests exist yet.                                                                                                             |
| **Power Management**               | No explicit low-power or watchdog behavior implemented yet. Watchdog is a requirement.                                                                                                                                             |
| **Optimization**                   | Opportunity exists to reduce startup latency and shrink final binary by tuning linker script and trimming unused libraries.                                                                                                        |
| **CMake cleanup**                  | The cmake setup is ok, but could really use some refinement to clean up the integration of the W5500 ioLibrary_driver and either a patch or specific commit.                                                                       |
---

# Closing

This codebase is designed for clarity, reliability, and growth.  
It is **production capable**, assuming that additional hardware interfaces are finalized and final edge case handling (network loss, hardware faults) are addressed.

**Explicit instruction to future developers**:
- **Read the code**.
- **Understand the task structure** before adding complexity.
- **Preserve the principle** of static, memory-safe embedded C++ design.

---
