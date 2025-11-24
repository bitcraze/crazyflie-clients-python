---
title: Color LED tab
page_id: color_led_tab
sort_order: 9
---

The Color LED tab lets you control the Color LED deck(s) attached to your Crazyflie. Use it to test, select colors and adjust brightness. You can control one or multiple decks (together or separately), save your favorite colors to a palette, and see real-time messages from the deck about its status.

![cfclient color LED](/docs/images/cfclient_colorled.png)

The tab is divided into 3 sections:
1.  Deck Position
2.  Color Selection
3.  Deck Information


### 1. Deck Position
The drop down is automatically updated to show the version of the color deck connected to your Crazyflie: **bottom**, **top**, or **both**.
If you have both decks attached, you have the option to control them independently or simultaneously by switching between all three options.


### 2. Color Selection
Select the color you want to display on your Color LED deck(s). You can either:

* Enter a HEX value,
* Pick a color from the Hue/Saturation/Brightness (HSB) field, or
* Pick a color by clicking one of the color buttons in the color palette.

When you find a color you want to save, click the add (+) button to add it to your color palette. You can remove the color from the palette again by right clicking on it.


### 3. Deck Information
This field displays messages from the Color LED deck. For example: 

```
Throttling: Lowering intensity to lower temperature.
```