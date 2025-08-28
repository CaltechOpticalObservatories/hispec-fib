The WIZnet-PICO-LWIP-C example uses the iolibrary_driver at ce4a7b6  (Feb 20 2022)
The WIZnet-PICO-C example uses the iolibrary_driver at c86300e  (Apr 13 2025) but there is a bug in a `#if 1` 
that prevents their example from building for the 5500 pico 2

W5500 uses SPI0 on pins GP16-21

GP25 is user LED
GP29 is 3v3 ADC


Free:
I2C0 & I2C1
UART0
UART1


## JSON Parsing

### https://github.com/kripton/jsoncpp/tree/rp2xx

A branch tuned for the RP, gross

### https://github.com/rafagafe/json-maker & https://github.com/rafagafe/tiny-json

ultra compact, clunky interface, fall back to if run into codebase size issues

### https://github.com/nlohmann/json**
Let's play with the big kids first


## modbus

### https://github.com/danjperron/rp2040-modbus_example

### https://github.com/debevv/nanoMODBUS

### https://github.com/alejoseb/Modbus-PI-Pico-FreeRTOS/tree/main
