bl_info = {
	"name": "Imports inkscape SVG as blender mask",
	"author": "Iszotic",
	"version": (0, 0),
	"blender": (2, 78, 3),
	"location": "Image Editor > Mask editor",
	"description": "Imports inkscape SVG as blender mask, only paths with lines and cubicbeziers segments are supported",
	"warning": "",
	"wiki_url": "",
	"category": "Import-Export",
}

import bpy
from mathutils import *
from math import *
import xml.etree.ElementTree as ET
from svg.path import parse_path, Line, CubicBezier

def is_number(s):
	try:
		float(s)
		return True
	except:
		return False

def get_css_attrib(element, attr, value = ''): # Searchs in style then on attributes then it gives up to the default value
	try:
		R_value = get_style_attrib_value(element.attrib['style'], attr, value)
	except:
		try:
			R_value = getattr(element, attr)
		except:
			return value
	return R_value

def get_style_attrib_value(style, attr, value = ''):
	for e in style.split(';'):
		dot_split = e.split(':')
		if dot_split[0] == attr:
			return dot_split[1]
	return value
# SVG coordinates are (x, 1-y) in relation to blender
# The resolution gives a relative value of coordinates
def get_norm_coord(segment, attr, resolution): 
	try:
		coord = getattr(segment, attr)
	except:
		coord = getattr(segment, "start")
	return (
		coord.real/resolution[0], 
		1-coord.imag/resolution[1]
	)
# common operations once the last point of the spline is made
# It sets the fill of the spline based in fill css attributes
# Deselecting makes sure once the next vertex point is added to the layer mask
# it creates a new spline

def spline_finish(spline, fill):
	spline.use_fill = False if fill == 'none' else True
	#bpy.ops.mask.select_linked()
	#bpy.ops.mask.normals_make_consistent()
	bpy.ops.mask.select_all(action = 'DESELECT')



def make_point(prev_segment,segment, resolution, vertex_slide_param, actual_layer, extreme = "strart"):
	#Creates a vertex point with the start value of the segment
	loc = {"location": get_norm_coord(segment, extreme, resolution)}
	bpy.ops.mask.add_vertex_slide(MASK_OT_add_vertex=loc, MASK_OT_slide_point=vertex_slide_param)

	spline = actual_layer.splines[-1]
	point = spline.points[0] #API puts latest point created on index 0, fuuuuuu

	#If the segment is bezier then the point is bezier
	#If the segment is linear but before it was a bezier curve and it's connected then is a bezier point
	#If the segment is linear and before was linear, then is is a linear point
	bezier_before = type(prev_segment) == CubicBezier
	line_now = type(segment) == Line
	line_before = type(segment) == Line
	if prev_segment == False:
		connected = True
	else:
		connected = prev_segment.end == segment.start

		
	if (type(segment) == CubicBezier) or (bezier_before and line_now and connected):
		bpy.ops.mask.handle_type_set(type='FREE')
		if prev_segment == False or segment == prev_segment:
			handle_right_coord = get_norm_coord(segment, "start", resolution)
		elif connected: #makes sure to not use previous lagging handle
			handle_right_coord = get_norm_coord(prev_segment, "control2", resolution)
			if handle_right_coord == get_norm_coord(prev_segment, "start", resolution):
				handle_right_coord = get_norm_coord(segment, "start", resolution)
		else:
			handle_right_coord = get_norm_coord(segment, "start", resolution) 
		
		handle_left_coord = get_norm_coord(segment, "control1", resolution) #Leading handle
		if handle_left_coord == get_norm_coord(segment, "end", resolution):
			handle_left_coord = get_norm_coord(segment, "start", resolution)

		point.handle_left = Vector(handle_left_coord)
		point.handle_right = Vector(handle_right_coord)
	else:
		bpy.ops.mask.handle_type_set(type='VECTOR')

#First bezier point doesn't have the right previous segment aviable
#also Non-cyclic paths sets useless leading handle 

def complete_bezier(segment, point, resolution, cyclic= False):
	if type(segment) == CubicBezier:
		handle_right_coord = get_norm_coord(segment, "control2", resolution)
		point.handle_right = Vector(handle_right_coord)
	if not cyclic:
		handle_left_coord = get_norm_coord(segment, "end", resolution) 
		point.handle_left = Vector(handle_left_coord)

#Main function

def import_inksvg_to_blmask(context, filepath, keep_ratio):
	namespaces = {'svg':'http://www.w3.org/2000/svg',
	'inkscape':'http://www.inkscape.org/namespaces/inkscape'}

	#Deals with namespace in XML library
	def find_all(parent, tag_children):
		if use_ns:
			return parent.findall('svg:' + tag_children, namespaces)
		else:
			return parent.findall(tag_children)
	#Inkscape applies blend modes as filters so it searchs for the url# of filters in defs
	def get_bl_blend(ink_layer, filters):
		filterId = get_css_attrib(ink_layer, "filter", '')[5:-1]
		blend = ''
		for filt in filters:
			if filt.attrib["id"] == filterId:
				blend = find_all(filt, "feBlend")[0].attrib["mode"]
				break
		return {
			'multiply':'MUL',
			'darken': "DARKEN",
			'lighten': "LIGHTEN",
			'difference': "DIFFERENCE",
			'screen': "ADD",
			'': "MERGE_ADD"
		}[blend]

	print("running import svg as mask")
	f = open(filepath, 'r', encoding='utf-8')
	data = f.read()
	f.close()

	# would normally load the data here
	# print(data)
	try:
		root = ET.fromstring(data)
	except ValueError:
		print('Some unsolved namespaces messing around the parser or else')

	root_attr = root.attrib
	x_resolution = None

	#Checks if the SVG file is using namespaces
	if root.tag == 'svg':
		use_ns = False
	else:
		use_ns = True
	#The viewbox is the most acurate coordinates of the SVG file then it recurs to
	#The width and height of the SVG, if neither of those are available then it terminates
	try:
		viewbox = root_attr['viewBox'].split(' ')
		x_resolution = viewbox[2]
		y_resolution = viewbox[3]
	except:
		viewbox = [None for i in range(4)]
		print("Warning: No ViewBox")

	try:
		width = root_attr['width']
		height = root_attr['height']
		check1 = is_number(width) and viewbox[2] == None
		check2 = is_number(height) and viewbox[3] == None
		x_resolution = width if check1 else viewbox[2]
		y_resolution = height if check2 else viewbox[3]
	except:
		2 + 2

	if x_resolution == None:
		print("Error: No resolution")
		return('CANCELLED')

	x_resolution = float(x_resolution)
	y_resolution = float(y_resolution)

	ctx_area = context.area
	orig_type = ctx_area.type
	ctx_area.type = 'IMAGE_EDITOR'

	#Modifies the resolution in X to keep the aspect ratio of the SVG if the user wants
	if keep_ratio:
		svg_ratio = x_resolution/y_resolution
		image = ctx_area.spaces.active.image
		if image == None:
			UV_ratio = 1
		else:
			UV_ratio = image.generated_width/image.generated_height
		res_ratio = UV_ratio/svg_ratio
		x_resolution = x_resolution*(UV_ratio/svg_ratio)

	resolution = [x_resolution, y_resolution]
	# Makes sure there's a working mask
	try:
		active_mask = ctx_area.spaces.active.mask
	except:
		bpy.ops.mask.new()
		active_mask = bpy.data.masks[-1]
		ctx_area.spaces.active.mask = active_mask
		print("Warning: No active masks, creating new mask")

	vertex_slide_param = {"slide_feather":False, "is_new_point":True}
	# makes sure there's a filter variable in case all layers are set to inkscape normal blend
	try:
		defs = find_all(root, 'defs')[0]
		filters = find_all(defs, 'filter')
	except ValueError:
		filters = []

	non_g_paths = [] #Later feature for paths not in layer groups
	
	for mask_layer in root:

		if mask_layer.tag[-1] == 'g':
			if use_ns:
				name = mask_layer.attrib['{' + namespaces['inkscape'] + '}' + 'label' ]
			else:
				try:
					name = mask_layer.attrib['id']
				except:
					name = 'MaskLayer'
		elif mask_layer.tag[-4:] == 'path':
			non_g_paths.append(mask_layer)
		else:
			continue

		opacity = float(get_css_attrib(mask_layer, "opacity", 1.0))
		blend = get_bl_blend(mask_layer, filters)

		bpy.ops.mask.layer_new('INVOKE_AREA', name= name)
		actual_layer = active_mask.layers[-1]

		actual_layer.blend = blend
		actual_layer.alpha = opacity
		prev_end = False #Initial values
		start_spline = False
		prev_seg = False
        
        #it search for all elements in the inkscape layer

		for element in mask_layer.iter():
			try:
				fill = get_css_attrib(element, "fill")
			except:
				fill = True

			if element.tag[-4:] == 'path':
				pathd = element.attrib['d']
				parsed = parse_path(pathd)
				last_segment = parsed[-1]

				for segment in parsed:
					#When a non cyclic spline ends this part occurs
					if segment.start != prev_end and prev_end != False: 

						make_point(prev_seg, prev_seg, resolution, vertex_slide_param, actual_layer, "end")
						spline.use_cyclic = False
						start_spline = False
						prev_end = False
						last_point = spline.points[0]
						complete_bezier(prev_seg, last_point, resolution)
						spline_finish(spline, prev_fill)
						if segment == prev_seg:
							break

					make_point(prev_seg, segment, resolution, vertex_slide_param, actual_layer, "start")
					
					spline = actual_layer.splines[-1]
					point = spline.points[0]
					
					prev_end = segment.start if prev_end == False else prev_end
					start_spline = segment.start if start_spline == False else start_spline
					#When a cyclic spline ends this part occurs

					if segment.start == prev_end:
						if start_spline == segment.end:
							first_point = spline.points[-1]
							spline.use_cyclic = True
							start_spline = False
							prev_end = False
							complete_bezier(segment, first_point, resolution, spline.use_cyclic)
							spline_finish(spline, fill)
						elif segment == last_segment:
							parsed.append(last_segment)
							prev_end = segment.end
						else:
							prev_end = segment.end

					prev_seg = segment
					prev_fill = fill
			else:
				print("unsupported element")
	ctx_area.type = orig_type

	return {'FINISHED'}
	
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

#Blender stuff
class ImportSvgMask(Operator, ImportHelper):
	bl_idname = "import_addon.svg_mask"
	bl_label = "Import Inkscape SVG as Mask"

	filename_ext = ".svg"

	keep_ratio = BoolProperty(
			name="Keep aspect ratio",
			description="Keep aspect ratio of SVG instead of UV square space",
			default=True,
			)

	filter_glob = StringProperty(
			default="*.svg",
			options={'HIDDEN'},
			maxlen=255,
			)
	
	def execute(self, context):
		return import_inksvg_to_blmask(context, self.filepath, self.keep_ratio)

def menu_func_import(self, context):
	self.layout.operator(ImportSvgMask.bl_idname, text="SVG2MASK Import Operator")


def register():
	bpy.utils.register_class(ImportSvgMask)
	bpy.types.INFO_MT_file_import.append(menu_func_import)


def unregister():
	bpy.utils.unregister_class(ImportSvgMask)
	bpy.types.INFO_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
	register()
# test call
#    bpy.ops.import_addon.svg_mask()
