#!/usr/bin/env python
#qct-parse - changes made for python3 compatibility. WIP. 

#see this link for lxml goodness: http://www.ibm.com/developerworks/xml/library/x-hiperfparse/

from lxml import etree  #for reading XML file (you will need to install this with pip)
import argparse         #for parsing input args
import configparser		#grip frame data values from a config txt file
import gzip             #for opening gzip file
import logging          #for logging output
import collections      #for circular buffer
import os      			#for running ffmpeg and other terminal commands
import subprocess		#not currently used
import gc				#not currently used
import math				#used for rounding up buffer half
import sys				#system stuff
import re				#can't spell parse without re fam
from distutils import spawn #dependency checking

#check that we have required software installed
def dependencies():
	depends = ['ffmpeg','ffprobe']
	for d in depends:
		if spawn.find_executable(d) is None:
			print("Buddy, you gotta install " + d)
			sys.exit()
	return

#Creates timestamp for pkt_dts_time
def dts2ts(frame_pkt_dts_time):
    seconds = float(frame_pkt_dts_time)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours < 10:
        hours = "0" + str(int(hours))
    else:
        hours = str(int(hours))  
    if minutes < 10:
        minutes = "0" + str(int(minutes))
    else:
        minutes = str(int(minutes))
    secondsStr = str(round(seconds,4))
    if int(seconds) < 10:
        secondsStr = "0" + secondsStr
    else:
        seconds = str(minutes)
    while len(secondsStr) < 7:
        secondsStr = secondsStr + "0"
    timeStampString = hours + ":" + minutes + ":" + secondsStr
    return timeStampString

#initializes the log
def initLog(inputPath):
	logPath = inputPath + '.log'
	logging.basicConfig(filename=logPath,level=logging.INFO,format='%(asctime)s %(message)s')
	logging.info("Started QCT-Parse")
	
#finds stuff over/under threshold
def threshFinder(inFrame,args,startObj,pkt,tag,over,thumbPath,thumbDelay):
	tagValue = float(inFrame[tag])
	frame_pkt_dts_time = inFrame[pkt]
	if "MIN" in tag or "LOW" in tag:
		under = over
		if tagValue < float(under): #if the attribute is under usr set threshold
			timeStampString = dts2ts(frame_pkt_dts_time)
			logging.warning(tag + " is under " + str(under) + " with a value of " + str(tagValue) + " at duration " + timeStampString)
			if args.te and (thumbDelay > int(args.ted)): #if thumb export is turned on and there has been enough delay between this frame and the last exported thumb, then export a new thumb
				printThumb(args,tag,startObj,thumbPath,tagValue,timeStampString)
				thumbDelay = 0
			return True, thumbDelay #return true because it was over and thumbDelay
		else:
			return False, thumbDelay #return false because it was NOT over and thumbDelay
	else:
		if tagValue > float(over): #if the attribute is over usr set threshold
			timeStampString = dts2ts(frame_pkt_dts_time)
			logging.warning(tag + " is over " + str(over) + " with a value of " + str(tagValue) + " at duration " + timeStampString)
			if args.te and (thumbDelay > int(args.ted)): #if thumb export is turned on and there has been enough delay between this frame and the last exported thumb, then export a new thumb
				printThumb(args,tag,startObj,thumbPath,tagValue,timeStampString)
				thumbDelay = 0
			return True, thumbDelay #return true because it was over and thumbDelay
		else:
			return False, thumbDelay #return false because it was NOT over and thumbDelay

#print thumbnail images of overs/unders	
#Need to update - file naming convention has changed
def printThumb(args,tag,startObj,thumbPath,tagValue,timeStampString):
	####init some variables using the args list
	inputVid = startObj.replace(".qctools.xml.gz", "")
	if os.path.isfile(inputVid):
		baseName = os.path.basename(startObj)
		baseName = baseName.replace(".qctools.xml.gz", "")
		outputFramePath = os.path.join(thumbPath,baseName + "." + tag + "." + str(tagValue) + "." + timeStampString + ".png")
		ffoutputFramePath = outputFramePath.replace(":",".")
		#for windows we gotta see if that first : for the drive has been replaced by a dot and put it back
		match = ''
		match = re.search(r"[A-Z]\.\/",ffoutputFramePath) #matches pattern R./ which should be R:/ on windows
		if match:
			ffoutputFramePath = ffoutputFramePath.replace(".",":",1) #replace first instance of "." in string ffoutputFramePath
		ffmpegString = "ffmpeg -ss " + timeStampString + ' -i "' + inputVid +  '" -vframes 1 -s 720x486 -y "' + ffoutputFramePath + '"' #Hardcoded output frame size to 720x486 for now, need to infer from input eventually
		output = subprocess.Popen(ffmpegString,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True)
		out,err = output.communicate()
		if args.q is False:
			print(out)
			print(err)
	else:
		print("Input video file not found. Ensure video file is in the same directory as the QCTools report.")
		exit()
	return	
	
#detect bars	
def detectBars(args,startObj,pkt,durationStart,durationEnd,framesList,buffSize):
	with gzip.open(startObj) as xml:
		for event, elem in etree.iterparse(xml, events=('end',), tag='frame'): #iterparse the xml doc
			if elem.attrib['media_type'] == "video": #get just the video frames
				frame_pkt_dts_time = elem.attrib[pkt] #get the timestamps for the current frame we're looking at
				frameDict = {}  #start an empty dict for the new frame
				frameDict[pkt] = frame_pkt_dts_time  #give the dict the timestamp, which we have now
				for t in list(elem):    #iterating through each attribute for each element
					keySplit = t.attrib['key'].split(".")   #split the names by dots 
					keyName = str(keySplit[-1])             #get just the last word for the key name
					frameDict[keyName] = t.attrib['value']	#add each attribute to the frame dictionary
				framesList.append(frameDict)
				middleFrame = int(round(float(len(framesList))/2))	#i hate this calculation, but it gets us the middle index of the list as an integer
				if len(framesList) == buffSize:	#wait till the buffer is full to start detecting bars
					##This is where the bars detection magic actually happens
					bufferRange = list(range(0, buffSize))
					if float(framesList[middleFrame]['YMAX']) > 210 and float(framesList[middleFrame]['YMIN']) < 10 and float(framesList[middleFrame]['YDIF']) < 3.0:
						if durationStart == "":
							durationStart = float(framesList[middleFrame][pkt])
							print("Bars start at " + str(framesList[middleFrame][pkt]) + " (" + dts2ts(framesList[middleFrame][pkt]) + ")")							
						durationEnd = float(framesList[middleFrame][pkt])
					else:
						print("Bars ended at " + str(framesList[middleFrame][pkt]) + " (" + dts2ts(framesList[middleFrame][pkt]) + ")")							
						break
			elem.clear() #we're done with that element so let's get it outta memory
	return durationStart, durationEnd

def analyzeIt(args,profile,startObj,pkt,durationStart,durationEnd,thumbPath,thumbDelay,framesList,frameCount=0,overallFrameFail=0):
	kbeyond = {} #init a dict for each key which we'll use to track how often a given key is over
	fots = ""
	if args.t:
		kbeyond[args.t] = 0 
	else:
		for k,v in profile.items(): 
			kbeyond[k] = 0
	with gzip.open(startObj) as xml:	
		for event, elem in etree.iterparse(xml, events=('end',), tag='frame'): #iterparse the xml doc
			if elem.attrib['media_type'] == "video": 	#get just the video frames
				frameCount = frameCount + 1
				frame_pkt_dts_time = elem.attrib[pkt] 	#get the timestamps for the current frame we're looking at
				if frame_pkt_dts_time >= str(durationStart): 	#only work on frames that are after the start time
					if durationEnd:
						if float(frame_pkt_dts_time) > durationEnd:		#only work on frames that are before the end time
							print("started at " + str(durationStart) + " seconds and stopped at " + str(frame_pkt_dts_time) + " seconds (" + dts2ts(frame_pkt_dts_time) + ") or " + str(frameCount) + " frames!")
							break
					frameDict = {}  								#start an empty dict for the new frame
					frameDict[pkt] = frame_pkt_dts_time  			#make a key for the timestamp, which we have now
					for t in list(elem):    						#iterating through each attribute for each element
						keySplit = t.attrib['key'].split(".")   	#split the names by dots 
						keyName = str(keySplit[-1])             	#get just the last word for the key name
						if len(keyName) == 1:						#if it's psnr or mse, keyName is gonna be a single char
							keyName = '.'.join(keySplit[-2:])		#full attribute made by combining last 2 parts of split with a period in btw
						frameDict[keyName] = t.attrib['value']		#add each attribute to the frame dictionary
					framesList.append(frameDict)					#add this dict to our circular buffer
					if args.pr is True:	#display "timestamp: Tag Value" (654.754100: YMAX 229) to the terminal window
						print(framesList[-1][pkt] + ": " + args.t + " " + framesList[-1][args.t])
					#Now we can parse the frame data from the buffer!	
					if args.o or args.u and args.p is None: #if we're just doing a single tag
						tag = args.t
						if args.o:
							over = float(args.o)
						if args.u:
							over = float(args.u)
						#ACTAULLY DO THE THING ONCE FOR EACH TAG
						frameOver, thumbDelay = threshFinder(framesList[-1],args,startObj,pkt,tag,over,thumbPath,thumbDelay)
						if frameOver is True:
							kbeyond[tag] = kbeyond[tag] + 1 #note the over in the keyover dictionary
					elif args.p is not None: #if we're using a profile
						for k,v in profile.items():
							tag = k
							over = float(v)
							#ACTUALLY DO THE THING ONCE FOR EACH TAG
							frameOver, thumbDelay = threshFinder(framesList[-1],args,startObj,pkt,tag,over,thumbPath,thumbDelay)
							if frameOver is True:
								kbeyond[k] = kbeyond[k] + 1 #note the over in the key over dict
								if not frame_pkt_dts_time in fots: #make sure that we only count each over frame once
									overallFrameFail = overallFrameFail + 1
									fots = frame_pkt_dts_time #set it again so we don't dupe
					thumbDelay = thumbDelay + 1				
			elem.clear() #we're done with that element so let's get it outta memory
	return kbeyond, frameCount, overallFrameFail


#This function is admittedly very ugly, but what it puts out is very pretty. Need to revamp 	
def printresults(kbeyond,frameCount,overallFrameFail):
	if frameCount == 0:
		percentOverString = "0"
	else:
		print("")
		print("TotalFrames:\t" + str(frameCount))
		print("")
		print("By Tag:")
		print("")
		percentOverall = float(overallFrameFail) / float(frameCount)
		if percentOverall == 1:
			percentOverallString = "100"
		elif percentOverall == 0:
			percentOverallString = "0"
		elif percentOverall < 0.0001:
			percentOverallString = "<0.01"
		else:
			percentOverallString = str(percentOverall)
			percentOverallString = percentOverallString[2:4] + "." + percentOverallString[4:]
			if percentOverallString[0] == "0":
				percentOverallString = percentOverallString[1:]
				percentOverallString = percentOverallString[:4]
			else:
				percentOverallString = percentOverallString[:5]			
		for k,v in kbeyond.items():
			percentOver = float(kbeyond[k]) / float(frameCount)
			if percentOver == 1:
				percentOverString = "100"
			elif percentOver == 0:
				percentOverString = "0"
			elif percentOver < 0.0001:
				percentOverString = "<0.01"
			else:
				percentOverString = str(percentOver)
				percentOverString = percentOverString[2:4] + "." + percentOverString[4:]
				if percentOverString[0] == "0":
					percentOverString = percentOverString[1:]
					percentOverString = percentOverString[:4]
				else:
					percentOverString = percentOverString[:5]
			print(k + ":\t" + str(kbeyond[k]) + "\t" + percentOverString + "\t% of the total # of frames")
			print("")
		print("Overall:")
		print("")
		print("Frames With At Least One Fail:\t" + str(overallFrameFail) + "\t" + percentOverallString + "\t% of the total # of frames")
		print("")
		print("**************************")
		print("")
	return
	
def main():
	####init the stuff from the cli########
	parser = argparse.ArgumentParser(description="parses QCTools XML files for frames beyond broadcast values")
	parser.add_argument('-i','--input',dest='i', help="the path to the input qctools.xml.gz file")
	parser.add_argument('-t','--tagname',dest='t', help="the tag name you want to test, e.g. SATMAX")
	parser.add_argument('-o','--over',dest='o', help="the threshold overage number")
	parser.add_argument('-u','--under',dest='u', help="the threshold under number")
	parser.add_argument('-p','--profile',dest='p',default=None,help="use values from your qct-parse-config.txt file, provide profile/ template name, e.g. 'default'")
	parser.add_argument('-buff','--buffSize',dest='buff',default=11, help="Size of the circular buffer. if user enters an even number it'll default to the next largest number to make it odd (default size 11)")
	parser.add_argument('-te','--thumbExport',dest='te',action='store_true',default=False, help="export thumbnail")
	parser.add_argument('-ted','--thumbExportDelay',dest='ted',default=9000, help="minimum frames between exported thumbs")
	parser.add_argument('-tep','--thumbExportPath',dest='tep',default='', help="Path to thumb export. if ommitted, it uses the input basename")
	parser.add_argument('-ds','--durationStart',dest='ds',default=0, help="the duration in seconds to start analysis")
	parser.add_argument('-de','--durationEnd',dest='de',default=99999999, help="the duration in seconds to stop analysis")
	parser.add_argument('-bd','--barsDetection',dest='bd',action ='store_true',default=False, help="turns Bar Detection on and off")
	parser.add_argument('-pr','--print',dest='pr',action='store_true',default=False, help="print over/under frame data to console window")
	parser.add_argument('-q','--quiet',dest='q',action='store_true',default=False, help="hide ffmpeg output from console window")
	args = parser.parse_args()
	
	
	######Initialize values from the Config Parser
	profile = {} #init a dictionary where we'll store reference values from our config file
	#init a list of every tag available in a QCTools Report
	tagList = ["YMIN","YLOW","YAVG","YHIGH","YMAX","UMIN","ULOW","UAVG","UHIGH","UMAX","VMIN","VLOW","VAVG","VHIGH","VMAX","SATMIN","SATLOW","SATAVG","SATHIGH","SATMAX","HUEMED","HUEAVG","YDIF","UDIF","VDIF","TOUT","VREP","BRNG","mse_y","mse_u","mse_v","mse_avg","psnr_y","psnr_u","psnr_v","psnr_avg"]
	if args.p is not None:
		config = configparser.RawConfigParser(allow_no_value=True)
		dn, fn = os.path.split(os.path.abspath(__file__)) #grip the dir where ~this script~ is located, also where config.txt should be located
		config.read(os.path.join(dn,"qct-parse_config.txt")) #read in the config file
		template = args.p #get the profile/ section name from CLI
		for t in tagList: 			#loop thru every tag available and 
			try: 					#see if it's in the config section
				profile[t.replace("_",".")] = config.get(template,t) #if it is, replace _ necessary for config file with . which xml attributes use, assign the value in config
			except: #if no config tag exists, do nothing so we can move faster
				pass
	
	######Initialize some other stuff######
	startObj = args.i.replace("\\","/")
	buffSize = int(args.buff)   #cast the input buffer as an integer
	if buffSize%2 == 0:
		buffSize = buffSize + 1
	initLog(startObj)	#initialize the log
	overcount = 0	#init count of overs
	undercount = 0	#init count of unders
	count = 0		#init total frames counter
	framesList = collections.deque(maxlen=buffSize)		#init holding object for holding all frame data in a circular buffer. 
	bdFramesList = collections.deque(maxlen=buffSize) 	#init holding object for holding all frame data in a circular buffer. 
	thumbDelay = int(args.ted)	#get a seconds number for the delay in the original file btw exporting tags
	parentDir = os.path.dirname(startObj)
	baseName = os.path.basename(startObj)
	baseName = baseName.replace(".qctools.xml.gz", "")
	durationStart = args.ds
	durationEnd = args.de

	# we gotta find out if the qctools report has pkt_dts_time or pkt_pts_time ugh
	with gzip.open(startObj) as xml:    
		for event, elem in etree.iterparse(xml, events=('end',), tag='frame'):  # iterparse the xml doc
			if elem.attrib['media_type'] == "video":  # get just the video frames
				# we gotta find out if the qctools report has pkt_dts_time or pkt_pts_time ugh
				match = re.search(r"pkt_.ts_time", etree.tostring(elem).decode('utf-8'))
				if match:
					pkt = match.group()
					break

	#set the start and end duration times
	if args.bd:
		durationStart = ""				#if bar detection is turned on then we have to calculate this
		durationEnd = ""				#if bar detection is turned on then we have to calculate this
	elif args.ds:
		durationStart = float(args.ds) 	#The duration at which we start analyzing the file if no bar detection is selected
	elif not args.de == 99999999:
		durationEnd = float(args.de) 	#The duration at which we stop analyzing the file if no bar detection is selected
	
	
	#set the path for the thumbnail export	
	if args.tep and not args.te:
		print("Buddy, you specified a thumbnail export path without specifying that you wanted to export the thumbnails. Please either add '-te' to your cli call or delete '-tep [path]'")
	
	if args.tep: #if user supplied thumbExportPath, use that
	    thumbPath = str(args.tep)
	else:
		if args.t: #if they supplied a single tag
			if args.o: #if the supplied tag is looking for a threshold Over
				thumbPath = os.path.join(parentDir, str(args.t) + "." + str(args.o))
			elif args.u: #if the supplied tag was looking for a threshold Under
				thumbPath = os.path.join(parentDir, str(args.t) + "." + str(args.u))
		else: #if they're using a profile, put all thumbs in 1 dir
			thumbPath = os.path.join(parentDir, "ThumbExports")
	
	if args.te: #make the thumb export path if it doesn't already exist
		if not os.path.exists(thumbPath):
			os.makedirs(thumbPath)
	
	
	########Iterate Through the XML for Bars detection########
	if args.bd:
		print("")
		print("Starting Bars Detection on " + baseName)
		print("")
		durationStart,durationEnd = detectBars(args,startObj,pkt,durationStart,durationEnd,framesList,buffSize,)
	

	########Iterate Through the XML for General Analysis########
	print("")
	print("Starting Analysis on " + baseName)
	print("")
	kbeyond, frameCount, overallFrameFail = analyzeIt(args,profile,startObj,pkt,durationStart,durationEnd,thumbPath,thumbDelay,framesList)
	
	
	print("Finished Processing File: " + baseName + ".qctools.xml.gz")
	print("")
	
	
	#do some maths for the printout
	if args.o or args.u or args.p is not None:
		printresults(kbeyond,frameCount,overallFrameFail)
	
	return

dependencies()	
main()