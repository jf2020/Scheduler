# Scheduler - Domoticz Python Plugin
Multi zones heating thermostat weekly scheduler python plugin for Domoticz home automation system

A fork and an extension of 

## Prerequisites

- Make sure that your Domoticz supports Python plugins (https://www.domoticz.com/wiki/Using_Python_plugins)

## Installation

You can use [Plugins Manager](https://github.com/stas-demydiuk/domoticz-plugins-manager) for automatic installation or follow manual steps:

1. Clone repository into your domoticz plugins folder
```
cd domoticz/plugins
git clone https://github.com/jf2020/Scheduler.git 
```
2. Restart domoticz
3. Make sure that "Accept new Hardware Devices" is enabled in Domoticz settings
4. Go to "Hardware" page and add new item with type "Scheduler"
5. Set your server address and port to plugin settings

Once configured teh plugin will create appropriate domoticz devices. You will find these devices on `Setup -> Devices` page

Inspired by https://github.com/chaeron/thermostat

Easy UI for timers manipulation. Setup OnTime timers and manage TimerPlans. 

Plugin creates VirtualThermostat Device and takes controls over associated OnTime timers.

![image](https://user-images.githubusercontent.com/3448931/104951516-b84da580-59d3-11eb-9352-81169976b1df.png)

For example, family visiting country house on weekends only. On working days house operate only on low tarif hours.
It takes about 1 day to pre-heat house. High tarif hours are 7:00-10:00 and 17:00-21:00, so heating should be off.

![image](https://user-images.githubusercontent.com/3448931/104951409-7cb2db80-59d3-11eb-800f-d5d5e4ebc532.png)

It is possible to change timerplan and avoid reconfigurating in case of long vacation.
![image](https://user-images.githubusercontent.com/3448931/104952298-3e1e2080-59d5-11eb-8573-70804173ab34.png)

## Plugin update

1. Go to plugin folder and pull new version
```
cd domoticz/plugins/zigbee2mqtt
git pull
```
2. Restart domoticz
