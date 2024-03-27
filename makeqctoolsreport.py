#!/usr/bin/env python
#makeqctoolsreport.py v 0.2.0

import os
import subprocess
import sys
import re
import gzip
import shutil
import argparse
from distutils import spawn

#Context manager for changing the current working directory
class cd:
    def __init__(self, newPath):
        self.newPath = os.path.expanduser(newPath)

    def __enter__(self):
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.savedPath)

#check to see that we have the required software to run this script
def dependencies():
	depends = ['ffmpeg','ffprobe']
	for d in depends:
		if spawn.find_executable(d) is None:
			print("Buddy, you gotta install " + d)
			sys.exit()
	return

def parseInput(startObj,outPath):
	#print ffprobe output to txt file, we'll grep it later to see if we need to transcode for j2k/mxf
	if outPath is not None:
		ffdata = open(os.path.join(outPath,os.path.basename(startObj) + ".ffdata.txt"),"w")
	else:
		ffdata = open(startObj + ".ffdata.txt","w")
	nul = open(os.devnull,'w')
	subprocess.call(['ffprobe','-show_streams','-of','flat','-sexagesimal','-i',startObj], stdout=ffdata, stderr=nul)
	nul.close()
	ffdata.close()

	#find which stream is the video stream
	if outPath is not None:
		ffdata = open(os.path.join(outPath,os.path.basename(startObj) + ".ffdata.txt"),"r")
	else:
		ffdata = open(startObj + ".ffdata.txt","r")
	for line in ffdata:
		#find the line for video stream
		if re.search('.codec_type=\"video\"', line):
			#separate that line by periods, the formatting provided by ffprobe
			foolist = re.split(r'\.', line)
			#3rd part of that list is the video stream
			whichStreamVid = foolist[2]
	ffdata.close()

	#based on the vid stream we found, find the codec
	if outPath is not None:
		ffdata = open(os.path.join(outPath,os.path.basename(startObj) + ".ffdata.txt"),"r")
	else:
		ffdata = open(startObj + ".ffdata.txt","r")
	for line in ffdata:
		if re.search('streams.stream.' + whichStreamVid + '.codec_name=', line):
			#dunno why we gotta remove quotes twice but there ya go
			matches = [f[1:-1] for f in re.findall('".+?"', line)]
			codecName = matches[0]
	ffdata.close()
	
	if outPath is not None:
		os.remove(os.path.join(outPath,os.path.basename(startObj) + ".ffdata.txt"))
	else:
		os.remove(startObj + ".ffdata.txt") #only takes a string so cant send ffdata var idk

	#set some special strings to handle j2k/mxf files
	if codecName == 'jpeg2000':
		inputCodec = ' -vcodec libopenjpeg '
		filterstring = ' -vf tinterlace=mode=merge,setfield=bff '
	else:
		inputCodec = None
		filterstring = None
	return inputCodec, filterstring


def transcode(startObj,outPath):
	#transcode to .nut	
	ffmpegstring = ['ffmpeg'] 
	if inputCodec is not None:
		ffmpegstring.append(inputCodec)
	ffmpegstring.extend(['-vsync','0','-i',startObj,'-vcodec','rawvideo','-acodec','pcm_s24le'])
	if filterstring is not None:
		ffmpegstring.append(filterstring)
	if outPath is not None:
		outObj = os.path.join(outPath,os.path.basename(startObj) + '.temp1.nut')
	else:
		outObj = startObj + '.temp1.nut'
	ffmpegstring.extend(['-f','nut','-y',outObj])
	subprocess.call(ffmpegstring)

	
def get_audio_stream_count(startObj):
	audio_stream_count = subprocess.check_output(['ffprobe', '-v', 'error','-select_streams', 'a', '-show_entries', 'stream=index','-of', 'flat', startObj]).splitlines()
	return len(audio_stream_count)
	
	
def makeReport(startObj, outPath):
	with cd(os.path.dirname(startObj)): #change directory into folder where orig video is. necessary because movie= fails when there's a : in path, like on windows :(
		#here's where we use ffprobe to make the qctools report in regular xml
		print("writing ffprobe output to xml...")
		audio_tracks = get_audio_stream_count(startObj) #find out how many audio streams there are
		if audio_tracks > 0:
			#make the ffprobe for 1 or more audio tracks
			ffprobe_command = ['ffprobe','-loglevel','error','-f','lavfi','-i','movie=' + os.path.basename(startObj) + ':s=v+a[in0][in1],[in0]signalstats=stat=tout+vrep+brng,cropdetect=reset=1,split[a][b];[a]field=top[a1];[b]field=bottom[b1],[a1][b1]psnr[out0];[in1]ebur128=metadata=1[out1]','-show_frames','-show_versions','-of','xml=x=1:q=1','-noprivate']
		elif audio_tracks == 0:
			#make the ffprobe for 0 audio tracks
			ffprobe_command = ['ffprobe','-loglevel','error','-f','lavfi','-i','movie=' + os.path.basename(startObj) + ',signalstats=stat=tout+vrep+brng,cropdetect=reset=1,split[a][b];[a]field=top[a1];[b]field=bottom[b1],[a1][b1]psnr','-show_frames','-show_versions','-of','xml=x=1:q=1','-noprivate']
		if outPath is not None: #if we have specified an output path for the reports
			tmpxmlpath = os.path.join(outPath,os.path.basename(startObj) + '.qctools.xml')
		else: #here's the default output path
			tmpxmlpath = startObj + '.qctools.xml'
		tmpxml = open(tmpxmlpath,'w')
		fnull = open(os.devnull,'w')
		retcode = subprocess.call(ffprobe_command, stdout=tmpxml,stderr=fnull) #run the ffprobe command and send the stdout to the xml file we defined
		#foo, bar = retcode.communicate()
		tmpxml.close()

	#gzip that tmpxml file then delete the regular xml file cause we dont need it anymore
	print("gzip-ing ffprobe xml output")
	with open(tmpxmlpath, 'rb') as f_in, gzip.open(tmpxmlpath + '.gz','wb') as f_out: #open takes string args for file to open, not the file obj itself
		shutil.copyfileobj(f_in,f_out)
	os.remove(tmpxmlpath) #remove takes a full path string not a file obj (e.g. not tmpxml)
	if os.path.exists(startObj + '.temp1.nut'): #get rid of the intermediate nut file if we made one
		os.remove(startObj + '.temp1.nut')

def main():
	####init the stuff from the cli########
	parser = argparse.ArgumentParser(description="parses QCTools XML files for frames beyond broadcast values")
	parser.add_argument('-i','--input',dest='i',help="the path to the input video file")
	parser.add_argument('-rop','--reportOutputPath',dest='rop',default=None,help="the path where you want to save the report, default is same dir as input video")
	args = parser.parse_args()
	
	####do some string replacements for the windows folks####
	startObj = args.i.replace("\\","/")
	
	#make sure it's really real
	if not os.path.exists(startObj):
		print("")
		print("The input file " + startObj + " does not exist")
		sys.exit()
		
	if args.rop is not None:
		outPath = args.rop.replace("\\","/")
	else:
		outPath = None
	
	#figure out how we wanna process it
	inputCodec, filterstring = parseInput(startObj,outPath)
	
	#if it's a j2k file, we gotta transcode
	if inputCodec:
		if 'jpeg' in inputCodec:
			transcode(startObj,outPath)
			startObj = startObj + ".temp1.nut"
	makeReport(startObj,outPath)
		
dependencies()
main()