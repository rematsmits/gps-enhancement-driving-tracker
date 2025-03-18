import gpxpy
import logging
import datetime
from functions.js_date_format import format_time_for_js
from xml.etree import ElementTree as etree

# Configure logging
logger = logging.getLogger(__name__)

def build_gpx_from_coords(matched_coords, raw_points):
    """
    Build a GPX file from processed coordinates
    
    Args:
        matched_coords: List of coordinate dicts or tuples [(lat, lon), ...] or [{'lat': lat, 'lon': lon, ...}, ...]
        
    Returns:
        tuple: (gpx_xml, track_points_for_display)
    """
    if not matched_coords:
        logger.warning("No coordinates provided to build GPX")
        return None, []
    
    # Build GPX structure
    gpx_out = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx_out.tracks.append(gpx_track)
    seg = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(seg)
    
    # Get the actual time span from original points
    start_time = raw_points[0]['time'] if raw_points[0].get('time') else None
    end_time = raw_points[-1]['time'] if raw_points[-1].get('time') else None
    
    # Calculate the total real-world duration in seconds
    if start_time and end_time:
        total_duration = (end_time - start_time).total_seconds()
        logger.info(f"Original track duration: {total_duration:.2f} seconds")
    else:
        total_duration = None
    
    total_matched = len(matched_coords)
    logger.info(f"Distributing timestamps across {total_matched} points")
    
    # Check if matched_coords contains dictionaries or tuples
    is_dict_format = isinstance(matched_coords[0], dict) if matched_coords else False
    
    # Find nearest points and assign more accurate timing

    # For map-matched tracks, use a more sophisticated approach that preserves speed variations
    # Calculate distances along original track to better preserve timing
    total_dist_original = 0
    distances_original = [0]  # Distance at each point of the original track
    
    for i in range(1, len(raw_points)):
        p1 = raw_points[i-1]
        p2 = raw_points[i]
        d = ((p1['lat'] - p2['lat'])**2 + (p1['lon'] - p2['lon'])**2)**0.5  # Simple distance
        total_dist_original += d
        distances_original.append(total_dist_original)
    
    # Calculate distances along the matched track
    total_dist_matched = 0
    distances_matched = [0]  # Distance at each point of the matched track
    
    for i in range(1, len(matched_coords)):
        if is_dict_format:
            p1, p2 = matched_coords[i-1], matched_coords[i]
            d = ((p1['lat'] - p2['lat'])**2 + (p1['lon'] - p2['lon'])**2)**0.5
        else:
            p1, p2 = matched_coords[i-1], matched_coords[i]
            d = ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
        total_dist_matched += d
        distances_matched.append(total_dist_matched)
    
    # Now assign times based on relative distances
    for i, coord in enumerate(matched_coords):
        # Extract lat/lon based on format
        if is_dict_format:
            lat, lon = coord['lat'], coord['lon']
            speed = coord.get('speed')
        else:
            lat, lon = coord
            speed = None
            
        point = gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lon)
        
        # Add speed as an extension if available
        if speed is not None:
            # Add GPX extension for speed (in m/s)
            extensions = {}
            # Convert speed back to m/s for GPX standard
            speed_ms = speed / 3.6 if speed is not None else None
            if speed_ms is not None:
                extensions['speed'] = str(speed_ms)
            
            if extensions:
                # Create GPX extensions
                gpx_ext = etree.Element('extensions')
                for key, value in extensions.items():
                    ext_elem = etree.SubElement(gpx_ext, key)
                    ext_elem.text = value
                point.extensions.append(gpx_ext)
        
        if total_dist_original > 0 and total_duration:
            # Calculate relative position along the track as ratio
            rel_pos = distances_matched[i] / total_dist_matched if total_dist_matched > 0 else 0
            
            # Find corresponding position in original track
            orig_dist = rel_pos * total_dist_original
            
            # Find closest point in original track by distance
            best_idx = 0
            min_diff = float('inf')
            
            for j, d in enumerate(distances_original):
                diff = abs(d - orig_dist)
                if diff < min_diff:
                    min_diff = diff
                    best_idx = j
            
            # Interpolate time between closest points if needed
            if best_idx < len(raw_points) - 1 and distances_original[best_idx] < orig_dist:
                # We're between two original points, interpolate time
                p1 = raw_points[best_idx]
                p2 = raw_points[best_idx + 1]
                
                if p1.get('time') and p2.get('time'):
                    d1 = distances_original[best_idx]
                    d2 = distances_original[best_idx + 1]
                    
                    # Avoid division by zero
                    if d2 - d1 > 0:
                        ratio = (orig_dist - d1) / (d2 - d1)
                        dt = (p2['time'] - p1['time']).total_seconds()
                        point.time = p1['time'] + datetime.timedelta(seconds=ratio * dt)
                    else:
                        point.time = p1['time']
                else:
                    point.time = p1.get('time')
            else:
                # Direct mapping to an original point
                point.time = raw_points[best_idx].get('time')
        elif total_duration:
            # Fallback to old linear method
            fraction = i / (total_matched - 1) if total_matched > 1 else 0
            point.time = start_time + datetime.timedelta(seconds=fraction * total_duration)
        else:
            # No timing information
            point.time = None
            
        seg.points.append(point)
    
    # Convert to XML for download
    gpx_xml = gpx_out.to_xml()
    
    # Prepare track points for display
    track_points = []
    for pt in seg.points:
        point_data = {
            'lat': pt.latitude, 
            'lon': pt.longitude
        }
        if pt.time:
            point_data['time'] = format_time_for_js(pt.time)
            
        # Extract speed from extensions
        for ext in pt.extensions:
            for child in ext:
                if child.tag == 'speed':
                    try:
                        # Convert from m/s to km/h for display
                        speed_ms = float(child.text)
                        point_data['speed'] = round(speed_ms * 3.6, 1)  # m/s to km/h
                    except (ValueError, TypeError):
                        pass
                        
        track_points.append(point_data)
    
    return gpx_xml, track_points

def parse_gpx_file(gpx_contents, safe_datetime_func):
    """
    Parse GPX file contents and extract track points
    
    Args:
        gpx_contents: String containing GPX XML content
        safe_datetime_func: Function to safely convert datetime objects
        
    Returns:
        list: List of track points as dicts with lat, lon, time, and speed if available
    """
    try:
        gpx = gpxpy.parse(gpx_contents)
        
        # Extract track points
        raw_points = []
        for track in gpx.tracks:
            for segment in track.segments:
                for pt in segment.points:
                    point_data = {
                        'lat': pt.latitude,
                        'lon': pt.longitude,
                        'time': safe_datetime_func(pt.time)
                    }
                    
                    # Handle elevation if present
                    if pt.elevation is not None:
                        point_data['elevation'] = pt.elevation
                    
                    # Extract speed from extensions if available
                    for ext in pt.extensions:
                        for child in ext:
                            if child.tag == 'speed':
                                try:
                                    # Convert from m/s to km/h
                                    speed_ms = float(child.text)
                                    point_data['speed'] = speed_ms * 3.6  # m/s to km/h
                                except (ValueError, TypeError):
                                    pass
                    
                    raw_points.append(point_data)
        
        logger.info(f"Extracted {len(raw_points)} points from GPX file")
        return raw_points
    except Exception as e:
        logger.error(f"Error parsing GPX file: {str(e)}")
        return []
