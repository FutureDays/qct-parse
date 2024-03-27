#!/usr/bin/env python

#overcatch.py
#runs qct-parse 6 times:
#against each High, Med, Low profile for bars
#against each High, Med, Low profile for content
#takes input for single qctools report to process

import argparse
import subprocess
import os
import sys
import re
import configparser		#grip frame data values from a config txt file

def main():
	parser = argparse.ArgumentParser(description="runs input QCTools Report against high, medium, and low tolerance profiles, for bars and content")
	parser.add_argument('-i','--input',dest='i',help='The QCTools Report to process')
	parser.add_argument('-bd','--bardetection',dest='bd',action='store_true',default=False,help='run with or without bar detection, default is False')
	parser.add_argument('-bo','--barsonly',dest='bo',action='store_true',default=False,help="run on bars only, not content, default is False")
	parser.add_argument('-t','--tag',dest='t',default="YMAX",help="the tag to look for, default is YMAX")
	args = parser.parse_args()
	
	print("Starting analysis on " + os.path.basename(args.i))
	
	#set the profiles we want to run against the startObj
	profileList = ["highTolerance","midTolerance","lowTolerance"]
	profileDict = {} #init dictionary for profileName : tagValue
	config = configparser.RawConfigParser(allow_no_value=True) #init the library for reading a config file
	dn, fn = os.path.split(os.path.abspath(__file__)) #grip the dir where ~this script~ is located, also where config.txt should be located
	config.read(os.path.join(dn,"qct-parse_config.txt")) #read in the config file
	
	#make the dictionary of profileNames : tagValues
	for profile in profileList:
		try:
			profileDict[profile] = config.get(profile,args.t)
		except:
			print("Buddy, theres no tag threshold defined for " + args.t + " for the profile " + profile)
			print("Check the config file at " + os.path.join(dn,"qct-parse_config.txt"))
			print("")
			pass

	#these will be filled with our ourput strings for each profile, later
	barOutDict = {}
	contentOutDict = {}

	#creates a log file in directory of startObj with name of [startObj]-overcatch.txt
	#logfile = open(os.path.join(os.path.dirname(args.i),os.path.basename(args.i + "-overcatch.txt")),"a")
	
	#do it for bars
	if args.bd is True:
		for profile in profileList:
			sys.stdout.flush()
			output = subprocess.Popen(["python","qct-parse.py","-bd","-p",profile,"-i",args.i],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
			out = output.stdout.readlines() #grip the stdout of that call, intelligently parse tabs and newlines
			for f in out:
				match = ''
				match = re.match(args.t + ".*$", f) #find just the tag name
				if match:
					barOutDict[profile] = match.group() #add the output, in string form, to our dict with key of the profile name
	
	#do it for content
	if args.bo is False:
		for profile in profileList:
			sys.stdout.flush()
			output = subprocess.Popen(["python","qct-parse.py","-p",profile,"-i",args.i],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
			out = output.stdout.readlines()
			for f in out:
				match = ''
				match = re.match(args.t + ".*$", f)
				if match:
					contentOutDict[profile] = match.group() 
	
	printout(barOutDict,contentOutDict,profileDict)
		

def printout(barOutDict,contentOutDict,profileDict):
	if barOutDict:
		print("")
		print("For bars")
		for bod in barOutDict:
			print("Frames beyond " + profileDict[bod] + " for " + barOutDict[bod])
	if contentOutDict:
		print("")
		print("For content")
		for cod in contentOutDict:
			print("Frames beyond " + profileDict[cod] + " for " + contentOutDict[cod])

main()
