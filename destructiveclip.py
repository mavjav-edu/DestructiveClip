#!/usr/bin/env python
'''
  ---DESTRUCTIVE Clip---
  An Inkscape Extension which works like Object|Clip|Set except that the paths clipped are actually *modified*
  Thus the clipping is included when exported, for example as a DXF file.
  Select two or more *paths* then choose Extensions|Modify path|Destructive clip.  The topmost path will be used to clip the others.
  Notes:-
    * Curves in paths are not supported (use Flatten Beziers).
    * Non-path objects in the selection will be ignored.  Use Object|Ungroup.
    * Paths entirely outside the clipping path will remain untouched (rather than modifying them to an empty path)
    * Complex paths may take a while (there seems to be no way too show progress)
    * Yes, using MBR's to do gross clipping might make it faster
    * No, Python is not my first language (C/C++ is)

  Mark Wilson Feb 2016

  ----

   Edits by Windell H. Oskay, www.evilmadscientit.com, August 2020
        Update calls to Inkscape 1.0 extension API to avoid deprecation warnings
        Minimal standardization of python whitespace
        Handle some errors more gracefully

'''

import inkex
import sys


class DestructiveClip(inkex.Effect):
    """An Inkscape Extension which works like Object|Clip|Set except that the paths clipped are actually *modified*.

    Thus, the clipping is included when exported, for example as a DXF file.  Select two or more *paths* then choose Extensions|Modify path|Destructive clip.  The topmost path will be used to clip the others.
    """
    def __init__(self):
        self.TOLERANCE = 0.0001  # any two nums ≤ this will be considered equal 
        inkex.Effect.__init__(self)
        self.error_messages = []

        self.curve_error = 'Cnable to parse path.\nConsider removing curves '
        self.curve_error += 'with Extensions > Modify Path > Flatten Beziers...'

    def approx_equal(self, a:float, b:float) -> bool:
        """Returns True if a and b are within TOLERANCE of each other

        Args:
            a (float): first number
            b (float): second number

        Returns:
            bool: True if a and b are within TOLERANCE of each other
        """  
        
        return abs(a-b) <= self.TOLERANCE

    def mid_point(self, line:inkex.Line) -> list[float]:
        """Returns the midpoint (x,y) of a line segment

        Args:
            line (inkex.Line): a line in the form ((x₁, y₁), (x₂, y₂))

        Returns:
            list: the midpoint of the line segment as a 2d list of the form (x,y)
        """        
        # mid_point of line
        return [(line[0][0] + line[1][0])/2, (line[0][1] + line[1][1])/2]

    def max_x(self, line_segments:list[inkex.Line]) -> float:
        """Returns the maximum x value of a list of line segments

        Args:
            line_segments (list[inkex.Line]): a list of line segments in the form ((x₁, y₁), (x₂, y₂))

        Returns:
            float: the maximum x value of the line segments
        """        
        # return max _x coord of line_segments
        maxx = 0.0
        for line in line_segments:
            maxx = max(maxx, line[0][0])
            maxx = max(maxx, line[1][0])
        return maxx

    def simple_path_to_line_segments(self, path: inkex.Path) -> tuple[list[inkex.Line],set[str]]:
        """takes a simple_path and converts to line *segments*, for simplicity.

        Thus [_move_to _p0, _line_to _p1, _line_to _p2] becomes [[_p0-_p1],[_p1,_p2]]
        only handles, Move, Line and Close.
        The simple_path library has already simplified things, normalized relative commands, etc.
        Args:
            path (inkex.Path): a simple_path

        Returns:
            tuple[list[inkex.Line],set[str]]: a tuple of the form (line_segments, error_messages)
        """
        line_segments = first = prev = this = []
        errors = set([])  # Similar errors will be stored only once
        for cmd in path:
            this = cmd[1]
            if cmd[0] == 'M': # moveto
                if first == []:
                    first = this
            elif cmd[0] == 'L': # lineto
                line_segments.append([prev, this])
            elif cmd[0] == 'Z': # close
                line_segments.append([prev, first])
                first = []
            elif cmd[0] == 'C':
                # https://developer.mozilla.org/en/docs/Web/SVG/Tutorial/Paths
                line_segments.append([prev, [this[4], this[5]]])
                errors.add("Curve node detected (svg type C), this node will be handled as a regular node")
            else:
                errors.add("Invalid node type detected: {}. This script only handle type M, L, Z".format(cmd[0]))
            prev = this
        return (line_segments, errors)

    def line_segments_to_simple_path(self, line_segments:list[inkex.Line]) -> inkex.Path:
        """_reverses simple_path_to_lines - converts line segments to move/line-to's

        Args:
            line_segments (list[inkex.Line]): a list of line segments in the form ((x₁, y₁), (x₂, y₂))

        Returns:
            inkex.Path: a simple path
        """        
        path = inkex.Path()
        end = None
        for line in line_segments:
            start = line[0]
            if end is None or not (self.approx_equal(end[0], start[0]) and self.approx_equal(end[1], start[1])):
                path.append(['M', start]) # only move if previous end not within TOLERANCE of this start
            end = line[1]
            path.append(['L', end])
        return path

    def line_intersection(self, l1_from, l1_to, l2_from, l2_to):
      
        # returns as [x, y] the intersection of the line L1From-L1To and L2From-L2To, or None
        # http://stackoverflow.com/questions/563198/how-do-you-detect-where-two-line-segments-intersect

        try:
            d_l1 = [l1_to[0] - l1_from[0], l1_to[1] - l1_from[1]]
            d_l2 = [l2_to[0] - l2_from[0], l2_to[1] - l2_from[1]]
        except IndexError:
            inkex.errormsg(self.curve_error)
            sys.exit()

        denominator = -d_l2[0]*d_l1[1] + d_l1[0]*d_l2[1]
        if not self.approx_equal(denominator, 0.0):
            s = (-d_l1[1]*(l1_from[0] - l2_from[0]) + d_l1[0]*(l1_from[1] - l2_from[1]))/denominator
            t = (+d_l2[0]*(l1_from[1] - l2_from[1]) - d_l2[1]*(l1_from[0] - l2_from[0]))/denominator
            if s >= 0.0 and s <= 1.0 and t >= 0.0 and t <= 1.0:
                return [l1_from[0] + (t * d_l1[0]), l1_from[1] + (t * d_l1[1])]
        else:
            return None

    def inside_region(self, point, line_segments, line_segments_max_x):
        """_summary_

        Args:
            point (_type_): _description_
            line_segments (_type_): _description_
            line_segments_max_x (_type_): _description_

        Returns:
            _type_: _description_
        """        
        # returns true if point is inside the region defined by line_segments.  line_segments_max_x is the maximum _x extent
        ray = [point, [line_segments_max_x*2.0, point[1]]]  # hz line to right of point, extending well outside _m_b_r
        crossings = 0
        for line in line_segments:
            if self.line_intersection(line[0], line[1], ray[0], ray[1]) is not None:
                crossings += 1
        return (crossings % 2) == 1  # odd number of crossings means inside

    def cull_segmented_line(self, segmented_line, line_segments, line_segments_max_x):
        """_summary_

        Args:
            segmented_line (_type_): _description_
            line_segments (_type_): _description_
            line_segments_max_x (_type_): _description_

        Returns:
            _type_: _description_
        """        
        # returns just the segments in segmented_line which are inside line_segments
        culled = []
        for segment in segmented_line:
            if self.inside_region(self.mid_point(segment), line_segments, line_segments_max_x):
                culled.append(segment)
        return culled

    def clip_line(self, line, line_segments):
        """_summary_

        Args:
            line (_type_): _description_
            line_segments (_type_): _description_

        Returns:
            _type_: _description_
        """        
        # returns line split where-ever lines in line_segments cross it
        lines_write = [line]
        for segment in line_segments:
            lines_read = lines_write
            lines_write = []
            for line in lines_read:
                intersect = self.line_intersection(line[0], line[1], segment[0], segment[1])
                if intersect is None:
                    lines_write.append(line)
                else: # split
                    lines_write.append([line[0], intersect])
                    lines_write.append([intersect, line[1]])
        return lines_write

    def clip_line_segments(self, line_segments_to_clip, clipping_line_segments):
        """return the lines in line_segments_to_clip clipped by the lines in clipping_line_segments

        Args:
            line_segments_to_clip (_type_): _description_
            clipping_line_segments (_type_): _description_

        Returns:
            _type_: _description_
        """    
        clipped_lines = []
        for line_to_clip in line_segments_to_clip:
            clipped_lines.extend(self.cull_segmented_line(self.clip_line(line_to_clip, clipping_line_segments), clipping_line_segments, self.max_x(clipping_line_segments)))
        return clipped_lines

    def effect(self):
        """Apply the destructive clip effect
        """        
        clipping_line_segments = None
        path_tag = inkex.addNS('path', 'svg')
        group_tag = inkex.addNS('g', 'svg')
        self.error_messages = []
        for id in self.options.ids:  # the selection, top-down
            node = self.svg.selected[id]
            if node.tag == path_tag:
                if clipping_line_segments is None: # first path is the clipper
                    (clipping_line_segments, errors) = self.simple_path_to_line_segments(node.path.to_arrays())
                    self.error_messages.extend(['{}: {}'.format(id, err) for err in errors])
                else:
                    # do all the work!
                    segments_to_clip, errors = self.simple_path_to_line_segments(node.path.to_arrays())
                    self.error_messages.extend(['{}: {}'.format(id, err) for err in errors])
                    clipped_segments = self.clip_line_segments(segments_to_clip, clipping_line_segments)
                    if len(clipped_segments) != 0:
                        path = str(inkex.Path(self.line_segments_to_simple_path(clipped_segments)))
                        node.set('d', path)
                    else:
                        # don't put back an empty path(?)  could perhaps put move, move?
                        inkex.errormsg('Object {} clipped to nothing, will not be updated.'.format(node.get('id')))
            elif node.tag == group_tag:  # we don't look inside groups for paths
                inkex.errormsg('Group object {} will be ignored. Please ungroup before running the script.'.format(id))
            else: # something else
                inkex.errormsg('_object {} is not of type path ({}), and will be ignored. _current type "{}".'.format(id, path_tag, node.tag))

        for error in self.error_messages:
            inkex.errormsg(error)

if __name__ == '__main__':
    DestructiveClip().run()
