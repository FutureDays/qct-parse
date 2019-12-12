# !/usr/bin/env python
# qct-parse 0.5.0

# for reading XML file (you will need to install this with pip)
# see this link for lxml goodness:
# http://www.ibm.com/developerworks/xml/library/x-hiperfparse/
from lxml import etree
# for parsing input args
import argparse
# grip frame data values from a config txt file
import configparser
# for opening gzip file
import gzip
# for logging output
import logging
import collections
# for circular buffer
import os
# for running ffmpeg and other terminal commands
import subprocess
# not currently used
import gc
# not currently used
import math
# used for rounding up buffer half
import sys
# system stuff
import re
# can't spell parse without re fam
from distutils import spawn


# dependency checking
# check that we have required software installed
def dependencies():
    depends = ['ffmpeg', 'ffprobe']
    for d in depends:
        if spawn.find_executable(d) is None:
            print("Buddy, you gotta install {}".format(d))
            sys.exit()
    return


# Creates timestamp for pkt_dts_time
def dts2ts(frame_pkt_dts_time):
    seconds = float(frame_pkt_dts_time)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    timeStampString = "%02d:%02d:%07.4f" % (hours, minutes, seconds)
    return timeStampString


# initializes the log
def initLog(inputPath):
    logPath = inputPath + '.log'
    logging.basicConfig(
        filename=logPath, level=logging.INFO, format='%(asctime)s %(message)s'
    )
    logging.info("Started QCT-Parse")


# finds stuff over/under threshold
def threshFinder(
    inFrame, args, startObj, pkt, tag, over, thumbPath, thumbDelay
):
    tagValue = float(inFrame[tag])
    frame_pkt_dts_time = inFrame[pkt]
    if "MIN" in tag or "LOW" in tag:
        under = over
        # if the attribute is under usr set threshold
        if tagValue < float(under):
            timeStampString = dts2ts(frame_pkt_dts_time)
            logging.warning(
                "{} is under {} with a value of {} at duration {}".format(
                    tag, str(under), str(tagValue), timeStampString
                )
            )
            # export thumb only if thumb export is on and there has been
            # enough delay between this frame and the last exported thumb
            if args.te and (thumbDelay > int(args.ted)):
                printThumb(
                    args, tag, startObj, thumbPath, tagValue, timeStampString
                )
                thumbDelay = 0
            # return true because it was over and thumbDelay
            return True, thumbDelay
        else:
            # return false because it was NOT over and thumbDelay
            return False, thumbDelay
    else:
        # if the attribute is over usr set threshold
        if tagValue > float(over):
            timeStampString = dts2ts(frame_pkt_dts_time)
            logging.warning(
                "{} is over {} with a value of {} at duration {}".format(
                    tag, str(over), str(tagValue), timeStampString
                )
            )
            # export thumb only if thumb export is turned on and there has
            # been enough delay between this frame and the last exported thumb
            if args.te and (thumbDelay > int(args.ted)):
                printThumb(
                    args, tag, startObj, thumbPath, tagValue, timeStampString
                )
                thumbDelay = 0
            # return true because it was over and thumbDelay
            return True, thumbDelay
        else:
            # return false because it was NOT over and thumbDelay
            return False, thumbDelay


# print thumbnail images of overs/unders
def printThumb(args, tag, startObj, thumbPath, tagValue, timeStampString):
    # init some variables using the args list
    inputVid = startObj.replace(".qctools.xml.gz", "")
    baseName = os.path.basename(startObj)
    baseName = baseName.replace(".qctools.xml.gz", "")
    outputFramePath = os.path.join(
        thumbPath,  + "{}.{}.{}.{}.png".format(
            baseName, tag, str(tagValue), timeStampString
        )
    )
    ffoutputFramePath = outputFramePath.replace(":", ".")
    # for windows we gotta see if that first : for the drive
    # has been replaced by a dot and put it back
    match = ''
    # matches pattern R./ which should be R:/ on windows
    match = re.search(r"[A-Z]\.\/", ffoutputFramePath)
    if match:
        # replace first instance of "." in string ffoutputFramePath
        ffoutputFramePath = ffoutputFramePath.replace(".", ":", 1)
    ffmpegString = "ffmpeg -ss {} -i {} -vframes 1 -s 720x486 -y {}".format(
        timeStampString, inputVid, ffoutputFramePath
    )
    output = subprocess.Popen(
        ffmpegString, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, shell=True
    )
    out, err = output.communicate()
    if args.q is False:
        print(out)
        print(err)
    return


# detect bars
def detectBars(
        args, startObj, pkt, durationStart, durationEnd,
        framesList, buffSize
):
    with gzip.open(startObj) as xml:
        # iterparse the xml doc
        for event, elem in etree.iterparse(xml, events=('end'), tag='frame'):
            # get just the video frames
            if elem.attrib['media_type'] == "video":
                # get the timestamps for the current frame we're looking at
                frame_pkt_dts_time = elem.attrib[pkt]
                # start an empty dict for the new frame
                frameDict = {}
                # give the dict the timestamp, which we have now
                frameDict[pkt] = frame_pkt_dts_time
                # iterating through each attribute for each element
                for t in list(elem):
                    # split the names by dots
                    keySplit = t.attrib['key'].split(".")
                    # get just the last word for the key name
                    keyName = str(keySplit[-1])
                    # add each attribute to the frame dictionary
                    frameDict[keyName] = t.attrib['value']
                framesList.append(frameDict)
                # i hate this calculation, but it gets us the
                # middle index of the list as an integer
                middleFrame = int(round(float(len(framesList))/2))
                # wait till the buffer is full to start detecting bars
                if len(framesList) == buffSize:
                    # This is where the bars detection magic actually happens
                    bufferRange = range(0, buffSize)
                    if (int(framesList[middleFrame]['YMAX']) > 210 and
                            int(framesList[middleFrame]['YMIN']) < 10 and
                            float(framesList[middleFrame]['YDIF']) < 3.0):

                        if durationStart == "":

                            durationStart = float(
                                framesList[middleFrame][pkt]
                            )
                            print("Bars start at {} ({})".format(
                                    str(framesList[middleFrame][pkt]),
                                    dts2ts(framesList[middleFrame][pkt])
                                )
                            )
                        durationEnd = float(framesList[middleFrame][pkt])
                    else:
                        print("Bars ended at {} ({})".format(
                                str(framesList[middleFrame][pkt]),
                                dts2ts(framesList[middleFrame][pkt])
                            )
                        )
                        break
            # we're done with that element so let's get it outta memory
            elem.clear()
    return durationStart, durationEnd


def analyzeIt(
    args, profile, startObj, pkt, durationStart, durationEnd,
    thumbPath, thumbDelay, framesList, frameCount=0, overallFrameFail=0
):
    # init a dict for each key which we'll use to track how often a
    # given key is over
    kbeyond = {}
    fots = ""
    if args.t:
        kbeyond[args.t] = 0
    else:
        for k, v in profile.items():
            kbeyond[k] = 0
    with gzip.open(startObj) as xml:
        # iterparse the xml doc
        for event, elem in etree.iterparse(xml, events=('end', ), tag='frame'):
            # get just the video frames
            if elem.attrib['media_type'] == "video":
                frameCount = frameCount + 1
                # get the timestamps for the current frame we're looking at
                frame_pkt_dts_time = elem.attrib[pkt]
                # only work on frames that are after the start time
                if float(frame_pkt_dts_time) >= durationStart:
                    # only work on frames that are before the end time
                    if float(frame_pkt_dts_time) > durationEnd:
                        print("started at {} seconds and stopped at {} seconds"
                              " ({}) or {} frames!".format(
                                str(durationStart), str(frame_pkt_dts_time),
                                dts2ts(frame_pkt_dts_time), str(frameCount)
                              )
                              )
                        break
                        # start an empty dict for the new frame
                    frameDict = {}
                    # make a key for the timestamp, which we have now
                    frameDict[pkt] = frame_pkt_dts_time
                    # iterating through each attribute for each element
                    for t in list(elem):
                        # split the names by dots
                        keySplit = t.attrib['key'].split(".")
                        # get just the last word for the key name
                        keyName = str(keySplit[-1])
                        # if it's psnr or mse, keyName is a single char
                        if len(keyName) == 1:
                            # full attribute made by combining last 2 parts
                            # of split with a period in btw
                            keyName = '.'.join(keySplit[-2:])
                        # add each attribute to the frame dictionary
                        frameDict[keyName] = t.attrib['value']
                    # add this dict to our circular buffer
                    framesList.append(frameDict)
                    # display "timestamp: Tag Value" (654.754100: YMAX 229)
                    # to the terminal window
                    if args.pr is True:
                        print("{}: {} {}".format(
                            framesList[-1][pkt], args.t, framesList[-1][args.t]
                        )
                        )
                    # Now we can parse the frame data from the buffer!
                    # if we're just doing a single tag
                    if args.o or args.u and args.p is None:
                        tag = args.t
                        if args.o:
                            over = float(args.o)
                        if args.u:
                            over = float(args.u)
                        # ACTUALLY DO THE THING ONCE FOR EACH TAG
                        frameOver, thumbDelay = threshFinder(
                            framesList[-1], args, startObj, pkt, tag, over,
                            thumbPath, thumbDelay
                        )
                        if frameOver is True:
                            # note the over in the keyover dictionary
                            kbeyond[tag] = kbeyond[tag] + 1
                    # if we're using a profile
                    elif args.p is not None:
                        for k, v in profile.items():
                            tag = k
                            over = float(v)
                            # ACTUALLY DO THE THING ONCE FOR EACH TAG
                            frameOver, thumbDelay = threshFinder(
                                framesList[-1], args, startObj, pkt, tag,
                                over, thumbPath, thumbDelay
                            )
                            if frameOver is True:
                                # note the over in the key over dict
                                kbeyond[k] = kbeyond[k] + 1
                                # make sure that we only count each over
                                # frame once
                                if frame_pkt_dts_time not in fots:
                                    overallFrameFail = overallFrameFail + 1
                                    # set it again so we don't dupe
                                    fots = frame_pkt_dts_time
                    thumbDelay = thumbDelay + 1
            # we're done with that element so let's get it outta memory
            elem.clear()
    return kbeyond, frameCount, overallFrameFail


# This function is admittedly very ugly, but what it puts out is very pretty.
# Need to revamp
def printresults(kbeyond, frameCount, overallFrameFail):
    if frameCount == 0:
        percentOverString = "0"
    else:
        print("\nTotalFrames:\t{}\n".format(str(frameCount)))
        print("By Tag:\n")
        percentOverall = float(overallFrameFail) / float(frameCount)
        if percentOverall < 0.0001:
            percentOverallString = "<0.01%"
        else:
            percentOverallString = '{0:.2%}'.format(percentOverall)
        for k, v in kbeyond.items():
            percentOver = float(kbeyond[k]) / float(frameCount)
            if percentOver < 0.0001:
                percentOverString = "<0.01%"
            else:
                percentOverString = '{0:.2%}'.format(percentOverall)
            print("{}: \t{}\t{}\t of the total # of frames\n".format(
                    k, str(kbeyond[k]), percentOverString
                )
            )
        print("Overall:\n")
        print("Frames With At Least One Fail:\t{}\t{}\t of the total"
              " # of frames\n".format(
                    str(overallFrameFail), percentOverallString
                )
              )
        print("**************************\n")
    return


def main():
    # init the stuff from the cli########
    parser = argparse.ArgumentParser(
        description="parses QCTools XML files for frames beyond broadcast"
        " values"
        )
    parser.add_argument(
        '-i', '--input',
        dest='i',
        help="the path to the input qctools.xml.gz file"
    )
    parser.add_argument(
        '-t', '--tagname',
        dest='t',
        help="the tag name you want to test, e.g. SATMAX"
    )
    parser.add_argument(
        '-o', '--over',
        dest='o',
        help="the threshold overage number"
    )
    parser.add_argument(
        '-u', '--under',
        dest='u',
        help="the threshold under number"
    )
    parser.add_argument(
        '-p', '--profile',
        dest='p',
        default=None,
        help="use values from your qct-parse-config.txt file, provide"
        " profile/ template name, e.g. 'default'"
    )
    parser.add_argument(
        '-buff', '--buffSize',
        dest='buff',
        default=11,
        help="Size of the circular buffer. if user enters an even number"
        " it'll default to the next largest number to make it odd"
        " (default size 11)"
    )
    parser.add_argument(
        '-te', '--thumbExport',
        dest='te', action='store_true',
        default=False,
        help="export thumbnail"
    )
    parser.add_argument(
        '-ted', '--thumbExportDelay',
        dest='ted',
        default=9000,
        help="minimum frames between exported thumbs"
    )
    parser.add_argument(
        '-tep', '--thumbExportPath',
        dest='tep',
        default='',
        help="Path to thumb export. if ommitted, it uses the input basename"
    )
    parser.add_argument(
        '-ds', '--durationStart',
        dest='ds',
        default=0,
        help="the duration in seconds to start analysis"
    )
    parser.add_argument(
        '-de', '--durationEnd',
        dest='de',
        default=99999999,
        help="the duration in seconds to stop analysis"
    )
    parser.add_argument(
        '-bd', '--barsDetection',
        dest='bd',
        action='store_true',
        default=False,
        help="turns Bar Detection on and off"
    )
    parser.add_argument(
        '-pr', '--print',
        dest='pr', action='store_true',
        default=False,
        help="print over/under frame data to console window"
    )
    parser.add_argument(
        '-q', '--quiet',
        dest='q', action='store_true',
        default=False,
        help="hide ffmpeg output from console window"
    )
    args = parser.parse_args()
    # Initialize values from the Config Parser
    # init a dictionary where we'll store reference values from our config file
    profile = {}
    # init a list of every tag available in a QCTools Report
    tagList = [
        "YMIN", "YLOW", "YAVG", "YHIGH", "YMAX", "UMIN", "ULOW", "UAVG",
        "UHIGH", "UMAX", "VMIN", "VLOW", "VAVG", "VHIGH", "VMAX", "SATMIN",
        "SATLOW", "SATAVG", "SATHIGH", "SATMAX", "HUEMED", "HUEAVG", "YDIF",
        "UDIF", "VDIF", "TOUT", "VREP", "BRNG", "mse_y", "mse_u", "mse_v",
        "mse_avg", "psnr_y", "psnr_u", "psnr_v", "psnr_avg"
    ]
    if args.p is not None:
        config = configparser.RawConfigParser(allow_no_value=True)
        # grip the dir where ~this script~ is located, also where config.txt
        # should be located
        dn, fn = os.path.split(os.path.abspath(__file__))
        # read in the config file
        config.read(os.path.join(dn, "qct-parse_config.txt"))
        # get the profile/ section name from CLI
        template = args.p
        # loop thru every tag available and
        for t in tagList:
            # see if it's in the config section
            try:
                # if it is, replace _ necessary for config file with . which
                # xml attributes use, assign the value in config
                profile[t.replace("_", ".")] = config.get(template, t)
            # if no config tag exists, do nothing so we can move faster
            except configparser.NoOptionError:
                pass
    # Initialize some other stuff######
    startObj = args.i.replace("\\", "/")
    # cast the input buffer as an integer
    buffSize = int(args.buff)
    if buffSize % 2 == 0:
        buffSize = buffSize + 1
    # initialize the log
    initLog(startObj)
    # init count of overs
    overcount = 0
    # init count of unders
    undercount = 0
    # init total frames counter
    count = 0
    # init holding object for holding all frame data in a circular buffer.
    framesList = collections.deque(maxlen=buffSize)
    # init holding object for holding all frame data in a circular buffer.
    bdFramesList = collections.deque(maxlen=buffSize)
    # get seconds number for delay in the original file btw exporting tags
    thumbDelay = int(args.ted)
    parentDir = os.path.dirname(startObj)
    baseName = os.path.basename(startObj)
    baseName = baseName.replace(".qctools.xml.gz", "")
    durationStart = args.ds
    durationEnd = args.de
    # find out if the qctools report has pkt_dts_time or pkt_pts_time ugh
    with gzip.open(startObj) as xml:
        # iterparse the xml doc
        for event, elem in etree.iterparse(xml, events=('end', ), tag='frame'):
            # get just the video frames
            if elem.attrib['media_type'] == "video":
                # we gotta find out if the qctools report has
                # pkt_dts_time or pkt_pts_time ugh
                match = ''
                match = re.search(r"pkt_.ts_time", str(etree.tostring(elem)))
                if match:
                    pkt = match.group()
                    break
    # set the start and end duration times
    if args.bd:
        # if bar detection is turned on then we have to calculate this
        durationStart = ""
        # if bar detection is turned on then we have to calculate this
        durationEnd = ""
    elif args.ds:
        # The duration at which we start analyzing the file if no bar
        # detection is selected
        durationStart = float(args.ds)
    elif not args.de == 99999999:
        # The duration at which we stop analyzing the file if no bar
        # detection is selected
        durationEnd = float(args.de)
    # set the path for the thumbnail export$
    if args.tep and not args.te:
        print("Buddy, you specified a thumbnail export path without"
              " specifying that you wanted to export the thumbnails. Please"
              " either add '-te' to your cli call or delete '-tep [path]'"
              )
    # if user supplied thumbExportPath, use that
    if args.tep:
        thumbPath = str(args.tep)
    else:
        # if they supplied a single tag
        if args.t:
            # if the supplied tag is looking for a threshold Over
            if args.o:
                thumbPath = os.path.join(
                    parentDir, "{}.{}".format(str(args.t), str(args.o))
                )
            # if the supplied tag was looking for a threshold Under
            elif args.u:
                thumbPath = os.path.join(
                    parentDir, "{}.{}".format(str(args.t), str(args.u))
                )
        # if they're using a profile, put all thumbs in 1 dir
        else:
            thumbPath = os.path.join(parentDir, "ThumbExports")
    # make the thumb export path if it doesn't already exist
    if args.te:
        if not os.path.exists(thumbPath):
            os.makedirs(thumbPath)
    # Iterate Through the XML for Bars detection########
    if args.bd:
        print("\nStarting Bars Detection on {}\n".format(baseName))
        durationStart, durationEnd = detectBars(
            args, startObj, pkt, durationStart, durationEnd,
            framesList, buffSize
        )
    # Iterate Through the XML for General Analysis########
    print("\nStarting Analysis on {}\n".format(baseName))
    kbeyond, frameCount, overallFrameFail = analyzeIt(
        args, profile, startObj, pkt, durationStart, durationEnd,
        thumbPath, thumbDelay, framesList
    )
    print("Finished Processing File: {}.qctools.xml.gz\n".format(baseName))
    # do some maths for the printout
    if args.o or args.u or args.p is not None:
        printresults(kbeyond, frameCount, overallFrameFail)
    return


dependencies()
main()
