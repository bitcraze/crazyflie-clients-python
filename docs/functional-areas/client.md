---
title: Bootloader client implementation
page_id: bootloaderclient
---


## Bootloader file format


In order to make bootloading easier across platforms the different
firmwares are packaged together in a ZIP file that contains a manifest
describing which files are used for what. Here\'s an example of a
manifest, it should be called *manifest.json*:

    {
      "version": 1,
      "files": {
          "cflie.bin": {
            "platform": "cf2",
            "target": "stm32",
            "type": "fw"
          },
          "nrf_cf2.bin": {
            "platform": "cf2",
            "target": "nrf51",
            "type": "fw"
          },
          "nrf_cload.bin": {
            "platform": "cf2",
            "target": "nrf51",
            "type": "bootloader"
          },
          "s110.bin": {
            "platform": "cf2",
            "target": "nrf51",
            "type": "softdevice"
          }
          "cf2_lua.bin": {
            "platform": "cf2",
            "target": "stm32",
            "type": "userapp",
            "origin": 524288
          }
       }
    }

Each entry in the file describes one file, with the following
attributes:


|  Attribute  | Values                            |Comments|
| --------------- | ------------------------------------- | ---------------------- |
|  platform       | cf2, tag                              |Select the target platform (tag = Roadrunner) |
|  target         | stm32, nrf51                          |Select the target MCU on the target platform|
|  type           | fw, bootloader, softdevice, userapp   |Describe what\'s contained in the binary|
|  origin         | N/A                                   |Set the address where the app should be flashed|


Currently only platform=cf2, target=stm32, target=nrf51 and type=fw is
supported.
