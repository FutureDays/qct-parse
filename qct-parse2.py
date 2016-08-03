#qct-parse2
#import xml.etree.ElementTree as etree
from lxml import etree
xml = "S:/avlab/qct-parse/cpb-aacip-507-9p2w37mc70.mxf.qctools.xml"
path = []
overdict = {}
for event, elem in etree.iterparse(xml, events=('end',), tag='frame'):
	if elem.attrib['media_type'] == "video":
		for t in list(elem):
			if t.attrib['key'] == 'lavfi.signalstats.YMAX':
				if int(t.attrib['value']) > 239:
					overdict[elem.attrib['best_effort_timestamp_time']] = t.attrib['value']
					#foo = raw_input("eh")
	elem.clear()
print len(overdict)
#if event == 'start':
#		path.append(elem.tag)
#		if elem.tag == 'tag':
#			if elem.attrib['key'] == 'lavfi.signalstats.YMAX':
#				print path
#				#if elem.attrib['value'] >= 233:
#					#framelist.append