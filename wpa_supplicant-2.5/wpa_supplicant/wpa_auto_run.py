#!/usr/bin/python3

import subprocess
import signal
import os
import time
import webbrowser 
import sqlite3
import json
import sys, getopt
import argparse
from urllib.parse import urlparse
import urllib
import os.path
import re
import _thread

global conf_file
db_name = 'peer_connection_db'
conn_tbl = 'connections'
config_file = "wpa_supplicant.conf"
target_file = config_file+'.tmp'
noob_conf_file='eapoob.conf'
keyword = 'Direction'
oob_out_file = '/tmp/noob_output.txt'


def change_config(peerID):

	if peerID is None:
		print ("Peer ID is NULL")
		return

	if os.path.isfile(config_file) is False:
		print ("Config file unavailable")
		return

	old_identity = peerID+'+s1@eap-noob.net'
	new_identity = peerID+'+s2@eap-noob.net'

	read_conf = open(config_file, 'r')
	write_conf = open(target_file,'w')

	conf_changed =0;

	for line in read_conf:
		if old_identity in line:
			line=line.replace(old_identity,new_identity)
			write_conf.write(line)
			conf_changed = 1
		else:
			write_conf.write(line)

	if conf_changed is 1:
		write_conf.close()
		read_conf.close()
		cmd = 'cp '+target_file+' '+config_file+'  ;  rm -f '+target_file
		runbash(cmd)
		reconfigure_peer()

def exec_query(cmd, qtype):

	retval = 0

	res = os.path.isfile(db_name)

	if True != res:
		#print ("No database file found")
		return 
	# create a DB connection 
	db_conn = sqlite3.connect(db_name)

	# check if DB cannot be accessed
	if db_conn is None:		 
		print ("DB busy")

	db_cur = db_conn.cursor() 	
      
	db_cur.execute(cmd)
	
	if qtype is 1:
		retval = db_cur.fetchone()
	elif qtype is 0:
		db_conn.commit()
	
	db_conn.close()
	return retval

def url_to_db(params):
	
	cmd = 'UPDATE connections SET noob ='+'\''+ params['Noob'][0]+'\''+' ,hoob =\''+params['Hoob'][0]+'\''+' where PeerID=\''+params['PeerID'][0]+'\'' 
	#print (cmd)

	exec_query(cmd,0)

def parse_qr_code(url):
	
	url_comp = urlparse(url);
	
	params = urllib.parse.parse_qs(url_comp.query)

	#print(params)	
	
	url_to_db(params)

	change_config(params['PeerID'][0])


def read_qr_code(arg):
	no_message = True
	#print("In new thread")
	cmd = "zbarcam >"+oob_out_file
	#runbash(cmd)
	subprocess.Popen(cmd,shell=True)

	while no_message:
        	time.sleep(2)
        	oob_output = open(oob_out_file,'r')
        	for line in oob_output:
                	if 'Noob' in line and 'Hoob' in line and 'PeerID' in line:
                        	no_message = False
        	oob_output.close()

	subprocess.Popen("sudo killall zbarcam",shell=True)
	cmd = 'rm -f '+oob_out_file
	runbash(cmd)
	print (line)
	parse_qr_code(line) 


def update_file(signum, frame):

	#print ('Updating File')
	con = sqlite3.connect(db_name)
	c = con.cursor()

	file = open("file.txt", "wb")
	for row in c.execute('select ssid,ServInfo,PeerID,Noob,Hoob,err_code from connections where show_OOB = 1'):
		#print (row[0] + '\n')
		servinfo = json.loads(row[1])
		
		if(row[5]!=0):
			file.write("Error code: "+str(row[5]))
		
		line = (row[0].encode(encoding='UTF-8') + b',' + servinfo['ServName'].encode(encoding='UTF-8') + b',' 
		+ servinfo['ServUrl'].encode(encoding='UTF-8')+b'/?PeerId='+row [2].encode(encoding='UTF-8') + 
		b'&Noob=' + row[3].encode(encoding='UTF-8')+ b'&Hoob=' + row[4].encode(encoding='UTF-8') + b'\n')
		file.write(line)
	file.close()
	con.close()
	return


def runbash(cmd):
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        out = p.stdout.read().strip()
        return out

def check_wpa():
	return os.path.isfile('wpa_supplicant')


def get_pid(arg):
	pid_list = []
	pname = arg.encode(encoding='UTF-8')
	p = runbash(b"ps -A | grep "+pname)
	if None == p:
		return None

	for line in p.splitlines():
		if pname in line:
			pid = int(line.split(None,1)[0])
			pid_list.append(pid)
	return pid_list

def prepare(iface):
	pid = get_pid('wpa_supplicant')
	for item in pid:
		os.kill(int(item),signal.SIGKILL)
	#now start your own wpa_supplicant
	
	print ("start wpa_supplicant")
	cmd = 'rm -f '+config_file+' touch '+config_file+' ; rm -f '+db_name
	runbash(cmd)		
	conf_file = open(config_file,'w')
	conf_file.write("ctrl_interface=/var/run/wpa_supplicant \n update_config=1\ndot11RSNAConfigPMKLifetime=120\n\n")
	conf_file.close()
	cmd = "./wpa_supplicant -i "+iface+" -c wpa_supplicant.conf -O /var/run/wpa_supplicant "
	subprocess.Popen(cmd,shell=True, stdout=1, stdin=None)

def network_scan():
	
	while True:
		result = runbash("./wpa_cli scan | grep OK")
		if 'OK' == result.decode():
			print ("scan OK")
			return
	
	
def get_result():
	scan_result = runbash("wpa_cli scan_result | awk '$4 ~ /WPA2-EAP/ {print $3,$5,$1}' | sort $1")
	conf_file = open(config_file,'a')
	token = ''
	ssid_list = []
	token_list = []
	for item in scan_result.decode():
		if '\n' == item:
			token_list.append(token)
			if token_list[1] not in ssid_list:
				ssid_list.append(token_list[1])  
				conf_file.write("network={\n\tssid=\""+token_list[1]+"\"\n\tbssid="+token_list[2]+"\n\tkey_mgmt=WPA-EAP\n\tpairwise=CCMP TKIP"
				"\n\tgroup=CCMP TKIP\n\teap=NOOB\n\tidentity=\"noob@eap-noob.net\"\n}\n\n")
				token = ''
			token_list[:] = []

		elif ' ' == item:
			token_list.append(token)		
			token = ''
		else:
			token += str(item)
	conf_file.close()
	return ssid_list 


def reconfigure_peer():
	pid = get_pid('wpa_supplicant')
	print ("Reconfigure wpa_supplicant")
	os.kill(int(pid[0]),signal.SIGHUP)

	
def check_result():
	res = runbash("./wpa_cli status | grep 'EAP state=SUCCESS'")
	if res == b"EAP state=SUCCESS":
		return True

	return False 

def launch_browser():
    	url = "test.html"
    	webbrowser.open(url,new=1,autoraise=True)
    	#signal.signal(signal.SIGUSR1, update_file)


def get_direction():
        noob_conf = open(noob_conf_file, 'r')

        for line in noob_conf:
                if '#' != line[0] and keyword in line:
                        parts = re.sub('[\s+]', '', line)
                        direction =  (parts[len(keyword)+1])

                        return direction

def terminate_supplicant():
	pid = get_pid('wpa_supplicant')
	os.kill(int(pid[0]),signal.SIGKILL)
	
def sigint_handler(signum, frame):
	terminate_supplicant()			
	exit(0)
	
def check_if_table_exists():
	#cmd = 'SELECT count(*) FROM information_schema.tables WHERE table_name=\''+conn_tbl+'\''
	cmd = 'SELECT name FROM sqlite_master WHERE type=\'table\''
	while True:
		out = exec_query(cmd,1)
		if out is not None and out[0] == conn_tbl:
			return
		time.sleep(3)
def main():

	interface=None
	no_result=0
	parser = argparse.ArgumentParser()
	parser.add_argument('-i', '--interface', dest='interface')
	args = parser.parse_args()

	if args.interface is None:
		print('Usage:wpa_auto_run.py -i <interface>')
		return

	if not(check_wpa()):
		print ("WPA_Supplicant not found")
		return

	interface=args.interface

	signal.signal(signal.SIGINT, sigint_handler)
	prepare(interface)
	time.sleep(2)
	network_scan()
	
	while True:
		ssid_list = get_result()
		if len(ssid_list) > 0:
			print (ssid_list)
			break
		time.sleep(2)
	
	reconfigure_peer()	

	direction = get_direction()
	check_if_table_exists()

	if direction is '2':
		print("Server to peer direction")
		_thread.start_new_thread(read_qr_code,(None,))
	elif direction is '1':
		print("Peer to server direction")
		launch_browser()
	else:
		print("No direction specified")
		terminate_supplicant()
		exit(0)


	while no_result == 0:
		if check_result():
			no_result =1
		time.sleep(5)
		if direction is '1':
			update_file(None,None)

	print ("***************************************EAP AUTH SUCCESSFUL *****************************************************")	
	cmd = 'sudo ifconfig '+interface+' 0.0.0.0 up ; dhclient '+interface   
	runbash(cmd)
	webbrowser.open_new_tab('https://www.youtube.com')

if __name__=='__main__':
    main()
