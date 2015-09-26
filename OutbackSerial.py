# -*- coding: utf-8 -*-
"""
Created on Sat Sep 26 14:06:26 2015

@author: Felix Darvas

"""

# inverter class for outback inverter ascii data processing
import time
from datetime import date
import MySQLdb as mdb
import os
import stat
import SocketServer
import threading,Queue

class SocketRequestHandler(SocketServer.BaseRequestHandler):
    def handle(self):
        # Echo the back to the client
        q=self.server.q;
        #print("request\n")
        if not q.empty(): 
            data_out=q.get()
            q.put(data_out)
            self.request.sendall(data_out)
        return
        

def setup_socket(server_address,q):
    try:
        os.unlink(server_address)
    except OSError:
        if os.path.exists(server_address):
            raise
    server = SocketServer.UnixStreamServer(server_address, SocketRequestHandler)
    os.chmod(server_address,stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
    server.q=q;
    t = threading.Thread(target=server.serve_forever)
    t.setDaemon(True) # don't hang on exit
    t.start()
    return server
    
def write_to_socket(socket,out):
    erg=False
    try: # write into uds 
        q,vv=socket.accept()
    except:
        q=None
    if q:
        #print("sending")
        try:
            q.recv(1024)
            erg=q.sendall(out) is None
        except Exception, e:
            print "exception is %s" % e
            print "some error while sending mate data to uds socket"
            #close and reopen socket
            erg=-10
            
        q.close()
    return erg
        
class inverter:
    fx_modes={'00':'Inv Off','01':'Search','02':'Inv On','03':'Charge','04':'Silent','05':'Float','06':'EQ','07':'Charger Off','08':'Support','09':'Sell Enabled','10':'Pass Thru','90':'FX Error','91':'AGS Error','92':'Com Error'} #list of modes the FX can be in
    fx_error_modes={0:'',1:'Low VAC output',2:'Stacking Error',3:'Over Temp.',4:'Low Battery',5:'Phase Loss',6:'High Battery',7:'Shorted ouput',8:'Back feed'} # list of error modes note that the index is the BIT #
    fx_ac_modes={'00':'No AC','01':'AC Drop','02':'AC Use'} # AC modes 
    fx_misc_modes={0:'',1:'230 V unit',2:'Reserved/used by FX',3:'Reserved/used by FX',4:'Reserved/used by FX',5:'Reserved/used by FX',6:'Reserved/used by FX',7:'Reserved/used by FX',8:'AUX output ON'} # list of misc modes nothe that the index is the BIT#
    fx_warning_modes={0:'',1:'AC Input Freq High',2:'AC Input Freq Low',3:'Input VAC High',4:'Input VAC Low',5:'Buy Amps > Input size',6:'Temp Sensor failed',7:'Comm Error',8:'Fan Failure'} # list of warnings index = BIT 
    
    def print_values(self):
        output='inverter '+str(self.address)+'\n'
        output=output+'AC_input '+str(self.ac_input_voltage)+'\n'
        output=output+'AC_output '+str(self.ac_output_voltage)+'\n'
        output=output+'buy_current '+str(self.buy_current)+'\n'
        output=output+'charge_current '+str(self.charge_current)+'\n'
        output=output+'energy '+str(self.energy)+'\n'
        output=output+'AC_mode '+str(self.fx_ac_mode)+'\n'
        output=output+'battery_voltage '+str(self.fx_battery_voltage)+'\n'
        output=output+'error_mode '+str(self.fx_error_mode)+'\n'
        output=output+'misc_mode '+str(self.fx_misc_mode)+'\n'
        output=output+'mode '+self.fx_operational_mode+'\n'
        output=output+'warning_mode '+str(self.fx_warning_mode)+'\n'
        output=output+'inverter_current '+str(self.inverter_current)+'\n'
        output=output+'power '+str(self.power)+'\n'
        output=output+'sell_current '+str(self.sell_current)+'\n'
        return output
    
    def send_data(self):
        if not self.q.empty():
            self.q.get() #dont spam the queue, only the current value is needed
        self.q.put(self.print_values())
  
    def update_energy(self):
        self.power=self.ac_output_voltage*self.inverter_current # power = ac output voltage * inverter sell current
        self.last_timestamp=self.current_timestamp
        self.current_timestamp=time.time()
        dt=self.current_timestamp-self.last_timestamp
        #print "{:03.1f}".format(dt)
        #print "sell current: %d" % self.sell_current
        #print "inverter current %d" % self.inverter_current
        #print "charge current %d" % self.charge_current
        
        self.energy=self.energy+(self.power*dt)/3600/1000 # energy in kWH 
        if self.host is not None: # if we have a database to post to
            if self.date !=date.toordinal(date.today()):
                con=mdb.connect(host=self.host,db=self.db,user=self.user,passwd=self.passwd)
                with con:
                    cur=con.cursor()
                    statement="INSERT INTO daily(time,energy,sunny) VALUES (%s, %s, %s)"    
                    cur.execute(statement,(date.fromordinal(self.date),self.energy))
                    con.commit()
                    cur.close()
                con.close()
                self.date=date.toordinal(date.today())
                self.energy=0
            
    def parse_data_string(self,data_string): # parse input data string from Mate
        items=data_string.split(',')
        chksum=-1
        try:
            chksum=int(items[13])
            for i in range(0,13):
                chksum=chksum-sum(map(int,items[i]))
        except:
            #print "checksum error!"
            #print data_string
            pass
        if chksum==0:
            try:
                self.address=int(items[0])
                self.inverter_current=float(items[1])
                self.charge_current=float(items[2])
                self.buy_current=float(items[3])
                self.ac_input_voltage=float(items[4])
                self.ac_output_voltage=float(items[5])
                self.sell_current=float(items[6])
                self.fx_operational_mode=self.fx_modes[items[7]]
                self.fx_error_mode=int(items[8])
                self.fx_ac_mode=self.fx_ac_modes[items[9]]
                self.fx_battery_voltage=float(items[10])/10
                self.fx_misc_mode=int(items[11])
                self.fx_warning_mode=int(items[12])
            except:
                print "checksum=0 still something wrong with FX string"
                print data_string
        else:
            self.serial_errorcount=self.serial_errorcount+1
        return chksum
        
    def __init__(self,system_battery_voltage=None,data_string=None,socket_address=None,host=None,db=None,user=None,passwd=None):
        self.host=host # MySql database info
        self.db=db
        self.user=user
        self.passwd=passwd
        self.ac_input_voltage     
        self.energy=0
        self.q=Queue.Queue()
        self.serial_errorcount=0
        if socket_address is None:
            self.socket=None
        else:        
            self.socket=setup_socket(socket_address,self.q)
            self.socket_address=socket_address
           # read previous data from file
        with open('/temp/inverter_energy','r') as f:
            read_data=f.readline()
            try:
                self.energy=float(read_data)
            except:
                print read_data
            read_data=f.readline()
            f.close()
        if system_battery_voltage is None:
            self.fx_system_battery_voltage=48.0 # default voltage of the battery
        else:
            self.fx_system_battery_voltage=system_battery_voltage # set entered system voltage
        if data_string is None:
            self.address=0 # outback inverter adress
            self.inverter_current=0.0 # current produced by the inverter
            self.charge_current=0.0 # current sent to the charger
            self.buy_current=0.0 # current bought from the grid
            self.ac_input_voltage=0.0 # AC input voltage
            self.ac_output_voltage=0.0 # AC output from the inverter
            self.sell_current=0.0 # AC current sold to the grid
            self.fx_operational_mode=self.fx_modes['00'] # default mode = off
            self.fx_error_mode=0 # default no error
            self.fx_ac_mode=self.fx_ac_modes['00'];
            self.fx_battery_voltage=0.0 # actual voltage
            self.fx_misc_mode=0 # default no misc mode set
            self.fx_warning_mode=0 # default no warning
        else:
            self.parse_data_string(data_string)
        self.power=self.ac_output_voltage*self.sell_current
        self.current_timestamp=time.time()
        self.last_timestamp=time.time()
        self.date=date.toordinal(date.today())


# charge controller class
class MX:
    mx_aux_modes={'00':'Disabled','01':'Diversion','02':'Remote','03':'Manual','04':'Vent Fan','05':'PV Trigger','06':'Float','07':'ERROR Output','08':'Night Light','09':'PWM Diversion','10':'Low Battery'} # MX Aux modes
    mx_error_modes={0:'',1:'',2:'',3:'',4:'',5:'',6:'Shorted Battery Sensor',7:'Too Hot',8:'High VOC'} # MX error modes, index = BIT #
    mx_charge_modes={'00':'Silent','01':'Float','02':'Bulk','03':'Absorb','04':'EQ'} # MX charge modes
    
    def print_values(self):
        output='MX '+str(self.address)+'\n'
        output=output+'battery_voltage '+str(self.battery_voltage)+'\n'
        output=output+'charger_current '+str(self.charger_current)+'\n'
        output=output+'daily_ah '+str(self.daily_ah)+'\n'
        output=output+'daily_kWH '+str(self.daily_kWH)+'\n'
        output=output+'mx_aux_mode '+self.mx_aux_mode+'\n'
        output=output+'mx_charge_mode '+self.mx_charge_mode+'\n'
        output=output+'mx_error_mode '+str(self.mx_error_mode)+'\n'
        output=output+'panel_voltage '+str(self.panel_voltage)+'\n'
        output=output+'power '+str(self.power)+'\n'
        output=output+'pv_current '+str(self.pv_current)+'\n'
        return output
    
    def send_data(self):
        if not self.q.empty():
            self.q.get() #dont spam the queue, only the current value is needed
        self.q.put(self.print_values())
    
        
    def parse_data_string(self,data_string):
        items=data_string.split(',')
        chksum=-1
        try:
            chksum=int(items[13])-ord(items[0])+48
            for i in range(1,13):
                chksum=chksum-sum(map(int,items[i]))
        except:
            pass
            #print "checksum error!\n"
            #print data_string
        if chksum==0:
            try:
                self.address=items[0]
                self.charger_current=float(items[2])+float(items[7])/10
                self.pv_current=float(items[3])
                self.panel_voltage=float(items[4])
                self.daily_kWH=float(items[5])/10
                self.mx_aux_mode=self.mx_aux_modes[items[7]]
                self.mx_error_mode=int(items[8])
                self.mx_charge_mode=self.mx_charge_modes[items[9]]
                self.battery_voltage=float(items[10])/10
                self.daily_ah=float(items[11])
                self.power=self.pv_current*self.panel_voltage
            except:
                print "checksum=0 still something wrong with MX string"
                print data_string
        else:
            self.serial_errorcount=self.serial_errorcount+1
        return chksum
        
    def __init__(self,data_string=None,socket_address=None):
        self.q=Queue.Queue()
        self.serial_errorcount=0
        if socket_address is None:
            self.socket=None
        else:        
            self.socket=setup_socket(socket_address,self.q)
            self.socket_address=socket_address
        if data_string is None:
            self.address='A' # address of the charge controller
            self.charger_current=0.0 # charger current
            self.pv_current=0.0 # PV current seen by the charge controller
            self.panel_voltage=0.0 # volatge of the panels
            self.daily_kWH=0.0 # kWH produced by the panels
            self.mx_aux_mode=self.mx_aux_modes['00'] # default aux mode
            self.mx_error_mode=0 # default no error
            self.mx_charge_mode=self.mx_charge_modes['00'] # default 'silent'
            self.battery_voltage=0.0 # default 0
            self.daily_ah=0.0 # daily Ah produced by the panels
        else:
            self.parse_data_string(data_string)
        self.power=self.pv_current*self.panel_voltage

class FlexNetDC:
    status_flags={0:'',1:'Charge Parameters met',2:'Relay mode:automatic',3:'Relay closed',4:'Shunt A negative',5:'Shunt B negative',6:'Shunt C negative'} # status bits
    extra_data_labels={0:'Accumulated AH shunt A',1:'Accumulated kWH shunt A',2:'Accumulated AH shunt B',3:'Accumulated kWH Shunt B',4:'Accumulated AH shunt C',5:'Accumulated kWH shunt C',6:'Days since full',7:'minimum SOC',8:'net input AH',9:'net output AH',10:'net input kWH',11:'net output kWH',12:'Charge factor battery - AH',13:'Charge factor battery kWH'} # what the extra data means
    def print_values(self):
        output='FnDC '+str(self.address)+'\n'
        output=output+'shuntA '+str(self.shuntA)+'\n'
        output=output+'shuntB '+str(self.shuntB)+'\n'
        output=output+'shuntC '+str(self.shuntC)+'\n'
        output=output+'extra_data '+str(self.extra_data_value)+'\n'
        output=output+'extra_data_label '+self.extra_data_label+'\n'
        output=output+'battery_voltage '+str(self.battery_voltage)+'\n'
        output=output+'soc '+str(self.soc)+'\n'
        output=output+'status '+str(self.status)+'\n'
        output=output+'shunt_enable '+str(self.shunt_enable)+'\n'
        output=output+'battery_temp '+str(self.battery_temp)+'\n'
        return output
        
    def send_data(self):
        if not self.q.empty():
            self.q.get() #dont spam the queue, only the current value is needed
        self.q.put(self.print_values())
            
        
    def parse_data_string(self,data_string):
        items=data_string.split(',')
        chksum=-1
        try:
            chksum=int(items[11])-ord(items[0])+48
            for i in range(1,11):
                chksum=chksum-sum(map(int,items[i]))
        except:
            pass
            #print "checksum error!"
            #print data_string
        if chksum==0:
            try:
                self.address=items[0]
                self.shuntA=float(items[1])
                self.shuntB=float(items[2])
                self.shuntC=float(items[3])
                extra_data_id=int(items[4])
                extra_data=float(items[5])
                if extra_data_id & (1 << 6): # bit 6 = negative value
                    extra_data=-extra_data
                extra_data_index=extra_data_id & 63
                self.extra_data_value=extra_data
                self.extra_data_label=self.extra_data_labels[extra_data_index]
                self.battery_voltage=float(items[6])/10;
                self.soc=float(items[7])
                self.status=int(items[9])
                self.shunt_enable=map(int,items[8])
                self.battery_temp=float(items[10])-10
            except:
                print "checksum=0 still something wrong with FNDC string"
                print data_string
        else:
            self.serial_errorcount=self.serial_errorcount+1
        return chksum
        
    def __init__(self,data_string=None,socket_address=None):
        self.q=Queue.Queue()
        self.serial_errorcount=0
        if socket_address is None:
            self.socket=None
        else:        
            self.socket=setup_socket(socket_address,self.q)
            self.socket_address=socket_address
        if data_string is None:
            self.address=''
            self.shuntA=0.0
            self.shuntB=0.0
            self.shuntC=0.0
            self.extra_data_value=0.0
            self.extra_data_label=self.extra_data_labels[0]
            self.battery_voltage=0.0
            self.soc=0.0
            self.status=0
            self.shunt_enable=[0,0,0]
            self.battery_temp=0.0
        else:
            self.parse_data_string(data_string)
    
