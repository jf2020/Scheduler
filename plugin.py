"""
<plugin key="Scheduler" name="Thermostat Scheduler" author="jf" version="1.0.0" wikilink="https://github.com/jf2020/Scheduler" externallink="https://github.com/jf2020/Scheduler">
    <description>
        <h2>Thermostat Scheduler</h2><br/>
        Thermostat with weekly scheduler.
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>User inteface for easy weeklyshedule editing</li>
            <li>Switch timerplans</li>
        </ul>
        <h3>Devices</h3>
        <ul style="list-style-type:square">
            <li>Device Type - Virtual Thermostat with timers.</li>
        </ul>
        <h3>Configuration</h3>
		Ensure Custom tab is enabled at Domoticz settings.
        Create Hardware, specify Domoticz connection and separate port.
        Enter a list of zones names using a comma separated list e.g.: Kitchen,Bedroom,Family Room
        Enter a list of temperature sensors for each zone in the same zone order e.g.: 14,18,23 (14 will be the temp sensor for kitchen, 18 for Bedroom, etc.)
        - you can use the same sensor for more than one zone e.g.: 14,18,14
        - you can use more than one sensor per zone by separating them by -. The resulting temp for that zone will be the average of the defined sensors. e.g; 14-15,18,23
        Enter a list of switches for each zone in the same order e.g.: 101,102,103
        - you can use more than one switch per zone by separating them by -. All switches associated with the same zone will be turned on or off. e.g; 14-15,18,23

        The plugin will create a thermostat device for each defined zone with the provided zone name. 
        You are responsible for creating the temperature sensors and switches to associate to each zone and providing their idx to the plugin. 

		Observe new menu item   "Heating Scheduler" under "Custom" tab.

		<h3>Prerequisites</h3>
		Plugin requires Domoticz-API module
		https://github.com/ArtBern/Domoticz-API
		<br/>
		Domoticz-API installation instruction:
		https://github.com/Xorfor/Domoticz-API/wiki/Installation
		
    </description>
    <params>
        <param field="Address" label="IP Address" width="180px" required="true" default="192.168.1.x"/>
        <param field="Port" label="Domoticz Port" width="60px" required="true" default="8080"/>
        <param field="Mode1" label="Listener Port" width="60px" required="true" default="9005"/>
        <param field="Mode2" label="Zones Thermostats (csv list of zone names)" width="600px" required="true" default="0"/>
        <param field="Mode3" label="Inside Temperature Sensors (csv list of idx)" width="200px" required="true" default="0"/>
        <param field="Mode4" label="Heating Switches (csv list of idx)" width="200px" required="true" default="0"/>
        <param field="Mode5" label="Outside Temperature Sensor" width="100px" required="false" default=""/>
        <param field="Mode6" label="Logging Level" width="200px">
            <options>
                <option label="Normal" value="Normal"  default="true"/>
                <option label="Verbose" value="Verbose"/>
                <option label="Debug - Python Only" value="2"/>
                <option label="Debug - Basic" value="62"/>
                <option label="Debug - Basic+Messages" value="126"/>
                <option label="Debug - Connections Only" value="16"/>
                <option label="Debug - Connections+Queue" value="144"/>
                <option label="Debug - All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
import urllib.parse
import os
import json
import base64
from urllib import parse, request
from utils import Utils

# sudo pip3 install git+git://github.com/ArtBern/Domoticz-API.git -t /usr/lib/python3.5 --upgrade
import DomoticzAPI as dom

#try:
    #apt-get install libmagic-dev
    #pip3 install python-libmagic
import magic
#except OSError as e:
#    Domoticz.Log ("Error loading python-libmagic: {0}:{1}".format(e.__class__.__name__, e.message))
#except AttributeError as e:
#    Domoticz.Log ("Error loading python-libmagic: {0}:{1}".format(e.__class__.__name__, e.message)) 


#pip3 install accept-types
from accept_types import get_best_match

class Zone:

    def __init__(self, name, thermostat, modeSelector, tempDetector, switch):
        self.name = name
        self.thermostat = thermostat
        self.modeSelector = modeSelector
        self.tempDetector = tempDetector
        self.switch = switch

    def __getTemp(self):
        return float(self.tempDetector.get_value("Temp"))

    def __getSwitchState(self):
        return self.switch.get_value("Status")

    def __getSetPoint(self):
        return float(self.thermostat.get_value("SetPoint"))

    def __setSwitchState(self, state):
        DomoticzAPICall("type=command&param=switchlight&idx={}&switchcmd={}".format(self.switch.get_value("idx"),state))
        # self.switch.set_value("Status", state)

    def process(self):
        temp = self.__getTemp()
        state = self.__getSwitchState()
        setPoint = self.__getSetPoint()
        # Domoticz.Log("Zone {}, Temp: {}, SetPoint: {}, State: {}".format(self.name,temp,setPoint,state))
        newState = "Off"
        offset = 0.1
        if ( state == "On" and temp < setPoint + offset ) or (state == "Off" and temp < setPoint - offset ) :
            # Domoticz.Log("Zone {} must heat".format(self.name))
            newState = "On"
        if newState != state :
            Domoticz.Log("Zone {} now {}".format(self.name, newState))
            self.__setSwitchState(newState)

class ZoneForJson:
    def __init__ (self, name, idx) :
        self.Name = name
        self.idx = idx


class BasePlugin:
    enabled = False
        
    httpServerConn = None
    httpServerConns = {}
    domServer = None

    
    def __init__(self):
        self.__filename = ""
        self.debug = False
        self.loglevel = None
        self.statussupported = True
        self.heartBeatCtr = 0
        self.zones = []

        self.InternalsDefaults = {
            'ComfortTemp': float(19), # temperature comfort
            'EcoTemp': float(17), # temperature eco
            'NightTemp': float(12), # temperature nuit
            'ConstC': float(60),  # inside heating coeff, depends on room size & power of your heater (60 by default)
            'ConstT': float(1),  # external heating coeff,depends on the insulation relative to the outside (1 by default)
            'nbCC': 0,  # number of learnings for ConstC
            'nbCT': 0,  # number of learnings for ConstT
            'LastPwr': 0,  # % power from last calculation
            'LastInT': float(0),  # inside temperature at last calculation
            'LastOutT': float(0),  # outside temprature at last calculation
            'LastSetPoint': float(20),  # setpoint at time of last calculation
            'ALStatus': 0}  # AutoLearning status (0 = uninitialized, 1 = initialized, 2 = disabled)
        self.Internals = self.InternalsDefaults.copy()
        return

    def onStart(self):
        Domoticz.Log("onStart called")
        # setup the appropriate logging level
        try:
            debuglevel = int(Parameters["Mode6"])
        except ValueError:
            debuglevel = 0
            self.loglevel = Parameters["Mode6"]
        if debuglevel != 0:
            self.debug = True
            Domoticz.Debugging(debuglevel)
            DumpConfigToLog()
            self.loglevel = "Verbose"
        else:
            self.debug = False
            Domoticz.Debugging(0)
        DumpConfigToLog()

        # loads persistent variables from dedicated user variable
        # note: to reset the thermostat to default values (i.e. ignore all past learning),
        # just delete the relevant "<plugin name>-InternalVariables" user variable Domoticz GUI and restart plugin
        self.getUserVar()

        self.httpServerConn = Domoticz.Connection(Name="Server Connection", Transport="TCP/IP", Protocol="HTTP", Port=Parameters["Mode1"])
        self.httpServerConn.Listen()
		
        self.__domServer = dom.Server(Parameters['Address'], Parameters['Port'])

        html = Utils.readFile(os.path.join(Parameters['HomeFolder'], 'web/html/thermostat_schedule.html'), False)
        javascript = Utils.readFile(os.path.join(Parameters['HomeFolder'], 'web/javascript/thermostat_schedule.js'), False)
        pointer = Utils.readFile(os.path.join(Parameters['HomeFolder'], 'web/images/downArrow_white.png'), True)
        pointerselected = Utils.readFile(os.path.join(Parameters['HomeFolder'], 'web/images/downArrow_red.png'), True)
        comfortIco = Utils.readFile(os.path.join(Parameters['HomeFolder'], 'web/images/comfort.png'), True)
        ecoIco = Utils.readFile(os.path.join(Parameters['HomeFolder'], 'web/images/eco.png'), True)
        nightIco = Utils.readFile(os.path.join(Parameters['HomeFolder'], 'web/images/night.png'), True)
        logo = Utils.readFile(os.path.join(Parameters['HomeFolder'], 'web/images/logo.png'), True)

        #json = Utils.readFile(os.path.join(Parameters['HomeFolder'], 'web/thermostat_schedule.json'), False)

        html = html.replace('src="../images/downArrow_white.png"', 'src="data:image/png;base64, ' + base64.b64encode(pointer).decode("ascii") + '"')
        html = html.replace('src="../images/downArrow_red.png"', 'src="data:image/png;base64, ' + base64.b64encode(pointerselected).decode("ascii") + '"')
        html = html.replace('"../images/comfort.png"', '"data:image/png;base64, ' + base64.b64encode(comfortIco).decode("ascii") + '"')
        html = html.replace('"../images/eco.png"', '"data:image/png;base64, ' + base64.b64encode(ecoIco).decode("ascii") + '"')
        html = html.replace('"../images/night.png"', '"data:image/png;base64, ' + base64.b64encode(nightIco).decode("ascii") + '"')
        html = html.replace('"../images/logo.png"', '"data:image/png;base64, ' + base64.b64encode(logo).decode("ascii") + '"')
        

        html = html.replace('<script src="../javascript/thermostat_schedule.js">', '<script>' + javascript)
        
        html = html.replace(' src="/', ' src="http://' + Parameters['Address'] + ':' + Parameters['Mode1'] + '/')
        html = html.replace(' href="/', ' href="http://' + Parameters['Address'] + ':' + Parameters['Mode1'] + '/')
        html = html.replace('"../thermostat_schedule.json"', '"http://' + Parameters['Address'] + ':' + Parameters['Mode1'] + '/thermostat_schedule.json"')
        html = html.replace('"../timer_plans.json"', '"http://' + Parameters['Address'] + ':' + Parameters['Mode1'] + '/timer_plans.json"')
        html = html.replace('"../zones.json"', '"http://' + Parameters['Address'] + ':' + Parameters['Mode1'] + '/zones.json"')
        html = html.replace('"/save"', '"http://' + Parameters['Address'] + ':' + Parameters['Mode1'] + '/save"')
        html = html.replace('"/changetimerplan"', '"http://' + Parameters['Address'] + ':' + Parameters['Mode1'] + '/changetimerplan"')
        html = html.replace('"/getschedule"', '"http://' + Parameters['Address'] + ':' + Parameters['Mode1'] + '/getschedule"')


        zoneNames = Parameters["Mode2"].split(",")
        idxTemps = Parameters["Mode3"].split(",")
        idxSwitches = Parameters["Mode4"].split(",")

        if len(zoneNames) == 0 :
            Domoticz.Error("At least one zone must be defined!")
        if len(zoneNames) != len(idxTemps) :
            Domoticz.Error("The number of Inside Temperature Sensors doesn't match the number of Zones")
        if len(zoneNames) != len(idxSwitches) :
            Domoticz.Error("The number of Heating Switches doesn't match the number of Zones")

        #delete if too many devices or wrong device type
        for i in range(len(Devices) - 1, 0, -1) :
            Devices[i].Delete()

        for i in range(len(Devices) - 1, 0, -1) :
            if i > len(zoneNames) * 2 :
                Devices[i].Delete()
            elif i % 2 == 1 and Devices[i].Type != 242 :
                Devices[i].Delete()
            elif i % 2 == 0 and Devices[i].Type != 244 :
                Devices[i].Delete()

        optionsModeZone = {"LevelActions": "||",
                       "LevelNames": "Off|Normal|Holiday",
                       "SelectorStyle": "0"}

        self.__thermostat = []
        for i, name in enumerate(zoneNames, start = 1):  # default start at 0, need 1
            unitId = i*2 - 1
            if unitId not in Devices :
                Domoticz.Device(Name=name, Unit=unitId, Type=242, Subtype=1, Used=1).Create()
                Devices[unitId].Update(nValue=0, sValue=str(self.Internals["EcoTemp"]), Name = name)
            else :
                dev = Devices[unitId]
                dev.Update(nValue=dev.nValue, sValue=dev.sValue, Name = name)

            unitId = i*2
            if unitId not in Devices :
                Domoticz.Device(Name="Mode" + name, Unit=unitId,  TypeName="Selector Switch", Switchtype=18, Image=15, Options=optionsModeZone, Used=1).Create()
                Devices[unitId].Update(nValue=0, sValue="10", Name = "Mode " + name)  # mode normal by default
            else :
                dev = Devices[unitId]
                dev.Update(nValue=dev.nValue, sValue=dev.sValue, Name = "Mode " + name)

            thermostat = dom.Device(self.__domServer, Devices[i*2-1].ID)
            modeSelector = dom.Device(self.__domServer, Devices[i*2].ID)
            self.__thermostat.append(thermostat)

            self.zones.append(Zone(name,\
                                   thermostat, \
                                   modeSelector, \
                                   dom.Device(self.__domServer, idxTemps[i-1]),\
                                   dom.Device(self.__domServer, idxSwitches[i-1])))

        for zone in self.zones :
            Domoticz.Log("Zone : {}, setPoint : {}, idxTemp : {}, idxSwitch : {}".format(zone.name,\
                                                                                         zone.thermostat.get_value("SetPoint"),\
                                                                                         zone.tempDetector.get_value("idx"),\
                                                                                         zone.switch.get_value("idx")))

        
        self.__filename = Parameters['StartupFolder'] + 'www/templates/Scheduler-' + "".join(x for x in Parameters['Name'] if x.isalnum()) + '.html'
        Utils.writeText(html, self.__filename)

        Domoticz.Log("Domoticz-API server is: " + str(self.__domServer))

        Domoticz.Log("Leaving on start")


    def onStop(self):
        LogMessage("onStop called")
        Utils.deleteFile(self.__filename)
        Domoticz.Debugging(0)
        LogMessage("Leaving onStop")


    def onConnect(self, Connection, Status, Description):
        if (Status == 0):
            Domoticz.Log("Connected successfully to: "+Connection.Address+":"+Connection.Port)
        else:
            Domoticz.Log("Failed to connect ("+str(Status)+") to: "+Connection.Address+":"+Connection.Port+" with error: "+Description)
        Domoticz.Log(str(Connection))

        self.httpServerConns[Connection.Name] = Connection

    def onMessage(self, Connection, Data):
        Domoticz.Log("onMessage called for connection: "+Connection.Address+":"+Connection.Port+":"+Connection.Name)
        DumpHTTPResponseToLog(Data)
        
        # Incoming Requests
        if "Verb" in Data:
            strVerb = Data["Verb"]
            #strData = Data["Data"].decode("utf-8", "ignore")
            LogMessage(strVerb+" request received.")
            data = "<!doctype html><html><head></head><body><h1>Successful GET!!!</h1><body></html>"
            if (strVerb == "GET"):

                strURL = Data["URL"]
                path = urllib.parse.unquote_plus(urllib.parse.urlparse(strURL).path)
                filePath = os.path.join(Parameters['HomeFolder'], "web" + path)

                with magic.Magic() as m:
                    mimetype = m.from_file(filePath)
                
                LogMessage("Mime type determined as " + mimetype)
                LogMessage("Path is " + path)

                return_type = mimetype

                if path == '/timer_plans.json':

                    plans = self.__domServer.timerplans
                    activeplan = self.__domServer.setting.get_value("ActiveTimerPlan")
                    
                    for plan in plans:
                        if (str(activeplan) == str(plan["idx"])):
                            plan["isactive"] = "true"
                        else:
                            plan["isactive"] = "false"
                            
                    timerplans = str(plans).replace("'", "\"").replace("True", "true").replace("False", "false")
                            
                    Connection.Send({"Status":"200", 
                                    "Headers": {"Connection": "keep-alive", 
                                                "Accept-Encoding": "gzip, deflate",
                                                "Access-Control-Allow-Origin":"http://" + Parameters['Address'] + ":" + Parameters['Port'] + "",
                                                "Cache-Control": "no-cache, no-store, must-revalidate",
                                                "Content-Type": "application/json; charset=UTF-8",
                                                "Content-Length":""+str(len(timerplans))+"",
                                                "Pragma": "no-cache",
                                                "Expires": "0"},
                                    "Data": timerplans})               

                elif path == '/zones.json':
                    zones = "[ "
                    sep = ""
                    for i,zone in enumerate(self.zones) :
                        zones = zones + sep + "{\"Name\": \"" + zone.name + "\", \"idx\": " + str(i) + " }"
                        sep = ", "
                    zones = zones + " ]"

                    Domoticz.Log("List zones json : {}".format(zones))
                    # zones = "[ {'Name': 'Cuisine', 'idx': 0 }, {'Name': 'Salon', 'idx': 1 }, {'Name': 'Chambre', 'idx': 2 } ]".replace("'", "\"")
                            
                    Connection.Send({"Status":"200", 
                                    "Headers": {"Connection": "keep-alive", 
                                                "Accept-Encoding": "gzip, deflate",
                                                "Access-Control-Allow-Origin":"http://" + Parameters['Address'] + ":" + Parameters['Port'] + "",
                                                "Cache-Control": "no-cache, no-store, must-revalidate",
                                                "Content-Type": "application/json; charset=UTF-8",
                                                "Content-Length":""+str(len(zones))+"",
                                                "Pragma": "no-cache",
                                                "Expires": "0"},
                                    "Data": zones})     

                elif (return_type == 'text/html' or return_type == 'text/css' or return_type == 'text/plain'):
                    data = Utils.readFile(filePath, False)
     
                    Connection.Send({"Status":"200", 
                                    "Headers": {"Connection": "keep-alive", 
                                                "Accept-Encoding": "gzip, deflate",
                                                "Access-Control-Allow-Origin":"http://" + Parameters['Address'] + ":" + Parameters['Port'] + "",
                                                "Cache-Control": "no-cache, no-store, must-revalidate",
                                                "Content-Type": return_type + "; charset=UTF-8",
                                                "Content-Length":""+str(len(data))+"",
                                                "Pragma": "no-cache",
                                                "Expires": "0"},
                                    "Data": data})

                elif return_type == 'image/png' or return_type == 'image/x-icon':
                    data = Utils.readFile(filePath, True)

                    LogMessage("Length is " + str(len(data)))
     
                    Connection.Send({"Status":"200", 
                                    "Headers": {"Connection": "keep-alive", 
                                                "Accept-Encoding": "gzip, deflate",
                                                "Access-Control-Allow-Origin":"http://" + Parameters['Address'] + ":" + Parameters['Port'] + "",
                                                "Cache-Control": "no-cache, no-store, must-revalidate",
                                                "Content-Type": return_type,
                                                "Pragma": "no-cache",
                                                "Expires": "0"},
                                    "Data": data})
                elif return_type == None:
                   Connection.Send({"Status":"406"}) 
                                
            elif (strVerb == "POST"):

                strURL = Data["URL"]
                path = urllib.parse.unquote_plus(urllib.parse.urlparse(strURL).path)

                jsn = Data["Data"]
                              
                if (path == "/save"):

                    j = json.loads(jsn)
                    zoneId = int(j["zone"])
                    newtimers = JsonToTimers(self.__thermostat[zoneId], jsn, self, Devices[zoneId * 2 + 1])

                    self.saveUserVar()
                    
                    oldtimers = dom.SetPointTimer.loadbythermostat(self.__thermostat[zoneId])
                    
                    for oldtimer in oldtimers:
                        if (oldtimer.timertype is dom.TimerTypes.TME_TYPE_ON_TIME):
                            oldtimer.delete()
                            
                    for newtimer in newtimers:
                        newtimer.add()

                elif (path == "/changetimerplan"):
                    
                    j = json.loads(jsn)
                                                         
                    self.__domServer.setting.set_value("ActiveTimerPlan", j["activetimerplan"])

                elif (path == "/getschedule"):
                    
                    j = json.loads(jsn)
                    zoneId = j["zone"]
                    thermostat = self.__thermostat[zoneId]
                    timers = dom.SetPointTimer.loadbythermostat(thermostat)
                    c = self.Internals['ComfortTemp']
                    e = self.Internals['EcoTemp']
                    n = self.Internals['NightTemp']
                    temps = thermostat.description.split(";")
                    if (len(temps) == 3) :
                        try :
                            lFloat = list(map(float,temps))
                            c = lFloat[0]
                            e = lFloat[1]
                            n = lFloat[2]
                        except Exception:
                            pass

                    data = str(TimersToJson(timers, c, e, n)).replace("'", "\"")
                                                         
                    Connection.Send({"Status":"200", 
                                "Headers": {"Connection": "keep-alive", 
                                            "Accept-Encoding": "gzip, deflate",
                                            "Access-Control-Allow-Origin":"http://" + Parameters['Address'] + ":" + Parameters['Port'] + "",
                                            "Cache-Control": "no-cache, no-store, must-revalidate",
                                            "Content-Type": "application/json; charset=UTF-8",
                                            "Content-Length":""+str(len(data))+"",
                                            "Pragma": "no-cache",
                                            "Expires": "0"},
                                "Data": data})
                                
                data = "{\"status\":\"OK\"}"
 
                Connection.Send({"Status":"200", 
                                "Headers": {"Connection": "keep-alive", 
                                            "Accept-Encoding": "gzip, deflate",
                                            "Access-Control-Allow-Origin":"http://" + Parameters['Address'] + ":" + Parameters['Port'] + "",
                                            "Cache-Control": "no-cache, no-store, must-revalidate",
                                            "Content-Type": "application/json; charset=UTF-8",
                                            "Content-Length":""+str(len(data))+"",
                                            "Pragma": "no-cache",
                                            "Expires": "0"},
                                "Data": data})
                

            elif (strVerb == "OPTIONS"):
                Connection.Send({"Status":"200 OK", 
                                "Headers": { 
                                            "Access-Control-Allow-Origin":"*",
                                            "Access-Control-Allow-Methods":"POST, GET, OPTIONS",
                                            "Access-Control-Max-Age":"86400",
                                            "Access-Control-Allow-Headers": "Content-Type",
                                            "Vary":"Accept-Encoding, Origin",
                                            "Content-Encoding": "gzip",
                                            "Content-Length": "0",
                                            "Keep-Alive": "timeout=2, max=100",
                                            "Connection": "Keep-Alive",
                                            "Content-Type": "text/plain"}
                                            })
            else:
                Domoticz.Error("Unknown verb in request: "+strVerb)

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))
        
        currentValue = self.__thermostat[0].get_value("SetPoint")
        if (str(currentValue) == str(Level)):
            return
        
        self.__thermostat[0].set_value("setpoint", Level)


    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Log("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Log("onDisconnect called for connection '"+Connection.Name+"'.")

        if Connection.Name in self.httpServerConns:
            del self.httpServerConns[Connection.Name]

    def onHeartbeat(self):
#        Domoticz.Log("onHeartbeat called")
        if self.heartBeatCtr == 6 :
            # Domoticz.Log("onHeartbeat do something")
            # do what must be done
            for zone in self.zones :
                zone.process()
            self.heartBeatCtr = 1
        else :
            self.heartBeatCtr += 1
        # Domoticz.Log("Leaving onHeartbeat")

        
#    def onDeviceModified(self, Unit):
#        Domoticz.Log("onCommand called for Unit " + str(Unit))

    def getUserVar(self):
        variables = DomoticzAPICall("type=command&param=getuservariables")
        if variables:
            # there is a valid response from the API but we do not know if our variable exists yet
            novar = True
            varname = Parameters["Name"] + "-InternalVariables"
            valuestring = ""
            if "result" in variables:
                for variable in variables["result"]:
                    if variable["Name"] == varname:
                        valuestring = variable["Value"]
                        novar = False
                        break
            if novar:
                # create user variable since it does not exist
                self.WriteLog("User Variable {} does not exist. Creation requested".format(varname), "Verbose")

                parameter = "adduservariable"
                
                # actually calling Domoticz API
                DomoticzAPICall("type=command&param={}&vname={}&vtype=2&vvalue={}".format(
                    parameter, varname, str(self.InternalsDefaults)))
                
                self.Internals = self.InternalsDefaults.copy()  # we re-initialize the internal variables
            else:
                try:
                    self.Internals.update(eval(valuestring))
                except:
                    self.Internals = self.InternalsDefaults.copy()
                return
        else:
            Domoticz.Error("Cannot read the uservariable holding the persistent variables")
            self.Internals = self.InternalsDefaults.copy()


    def saveUserVar(self):
        varname = Parameters["Name"] + "-InternalVariables"
        DomoticzAPICall("type=command&param=updateuservariable&vname={}&vtype=2&vvalue={}".format(
            varname, str(self.Internals)))

    def WriteLog(self, message, level="Normal"):
        if (self.loglevel == "Verbose" and level == "Verbose") or level == "Status":
            if self.statussupported:
                Domoticz.Status(message)
            else:
                Domoticz.Log(message)
        elif level == "Normal":
            Domoticz.Log(message)
       
      

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()
    
#def onDeviceModified(Unit):
    #global _plugin
    #_plugin.onDeviceModified(Unit)    

# Generic helper functions
def TimersToJson(timers, c, e, n):
    tmrdict = { "temps": {"C": c, "E": e,"N": n }, "monday": [], "tuesday": [], "wednesday": [], "thursday": [], "friday" : [], "saturday": [], "sunday": []}
    for timer in timers:
        if (timer.timertype == dom.TimerTypes.TME_TYPE_ON_TIME):
            if dom.TimerDays.Monday in timer.days:
                tmrdict["monday"].append([f"{timer.hour:02d}:{timer.minute:02d}", timer.temperature ])
            if dom.TimerDays.Tuesday in timer.days:
                tmrdict["tuesday"].append([f"{timer.hour:02d}:{timer.minute:02d}", timer.temperature ])
            if dom.TimerDays.Wednesday in timer.days:
                tmrdict["wednesday"].append([f"{timer.hour:02d}:{timer.minute:02d}", timer.temperature ])
            if dom.TimerDays.Thursday in timer.days:
                tmrdict["thursday"].append([f"{timer.hour:02d}:{timer.minute:02d}", timer.temperature ])
            if dom.TimerDays.Friday in timer.days:
                tmrdict["friday"].append([f"{timer.hour:02d}:{timer.minute:02d}", timer.temperature ])
            if dom.TimerDays.Saturday in timer.days:
                tmrdict["saturday"].append([f"{timer.hour:02d}:{timer.minute:02d}", timer.temperature ])
            if dom.TimerDays.Sunday in timer.days:
                tmrdict["sunday"].append([f"{timer.hour:02d}:{timer.minute:02d}", timer.temperature ])   
    return tmrdict
        
def JsonToTimers(device, data, plugin, pluginDevice):
    plan = json.loads(data)
    timers = []
    for day in plan:
        if day == "zone":
            continue
        if day == "temps":
            Domoticz.Log(str(plan[day]))
            pluginDevice.Update(nValue=pluginDevice.nValue, sValue=pluginDevice.sValue, Description=str(plan[day]["C"]) + ";" + str(plan[day]["E"]) + ";" + str(plan[day]["N"]))
            continue 
        timerday = dom.TimerDays[day.capitalize()]
        for tmr in plan[day]:
            timers.append(dom.SetPointTimer(device, Active=True, Days=timerday, Temperature=tmr[1], Time=tmr[0], Type=dom.TimerTypes.TME_TYPE_ON_TIME))
    
    return timers

# def parseCSV(strCSV):
#     listvals = []
#     i=0
#     for value in strCSV.split(","):
#         try:
#             if i == 5:
#                 val = float(value)
#             else:
#                 val = int(value)
#         except:
#             pass
#         else:
#             listvals.append(val)
#         i+=1
#     return listvals

def DomoticzAPICall(APICall):

    resultJson = None
    url = "http://{}:{}/json.htm?{}".format(Parameters["Address"], Parameters["Port"], parse.quote(APICall, safe="&="))
    Domoticz.Debug("Calling domoticz API: {}".format(url))
    try:
        req = request.Request(url)
        if Parameters["Username"] != "":
            Domoticz.Debug("Add authentification for user {}".format(Parameters["Username"]))
            credentials = ('%s:%s' % (Parameters["Username"], Parameters["Password"]))
            encoded_credentials = base64.b64encode(credentials.encode('ascii'))
            req.add_header('Authorization', 'Basic %s' % encoded_credentials.decode("ascii"))

        response = request.urlopen(req)
        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson["status"] != "OK":
                Domoticz.Error("Domoticz API returned an error: status = {}".format(resultJson["status"]))
                resultJson = None
        else:
            Domoticz.Error("Domoticz API: http error = {}".format(response.status))
    except:
        Domoticz.Error("Error calling '{}'".format(url))
    return resultJson

def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return
    
def LogMessage(Message):
    if Parameters["Mode6"] != "Normal":
        Domoticz.Log(Message)
    elif Parameters["Mode6"] != "Debug":
        Domoticz.Debug(Message)
    else:
        f = open("http.html","w")
        f.write(Message)
        f.close()   

def DumpHTTPResponseToLog(httpResp, level=0):
    if (level==0): Domoticz.Debug("HTTP Details ("+str(len(httpResp))+"):")
    indentStr = ""
    for x in range(level):
        indentStr += "----"
    if isinstance(httpResp, dict):
        for x in httpResp:
            if not isinstance(httpResp[x], dict) and not isinstance(httpResp[x], list):
                Domoticz.Debug(indentStr + ">'" + x + "':'" + str(httpResp[x]) + "'")
            else:
                Domoticz.Debug(indentStr + ">'" + x + "':")
                DumpHTTPResponseToLog(httpResp[x], level+1)
    elif isinstance(httpResp, list):
        for x in httpResp:
            Domoticz.Debug(indentStr + "['" + x + "']")
    else:
        Domoticz.Debug(indentStr + ">'" + x + "':'" + str(httpResp[x]) + "'")

