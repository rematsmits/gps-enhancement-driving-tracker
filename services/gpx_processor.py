import gpxpy
import logging
import datetime
from services.interpolator import format_time_for_js

# Configure logging
logger = logging.getLogger(__name__)

def build_gpx_from_coords(matched_coords, raw_points, skip_map_matching=False):
    """
    Build a GPX file from processed coordinates
    
    Args:
        matched_coords: List of coordinate tuples [(lat, lon), ...]
        raw_points: Original track points with timestamps
        skip_map_matching: Whether map matching was skipped
        
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
    start_time = raw_points[0]['time']
    end_time = raw_points[-1]['time']
    
    # Calculate the total real-world duration in seconds
    if start_time and end_time:
        total_duration = (end_time - start_time).total_seconds()
        logger.info(f"Original track duration: {total_duration:.2f} seconds")
    else:
        total_duration = None
    
    total_matched = len(matched_coords)
    logger.info(f"Distributing timestamps across {total_matched} points")
    
    for i, (lat, lon) in enumerate(matched_coords):
        # Create GPX point
        point = gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lon)
        
        # Assign time based on a more accurate linear interpolation
        if start_time and end_time and total_duration:
            # Calculate the time as a linear progression from start to end
            fraction = i / (total_matched - 1) if total_matched > 1 else 0
            point_time = start_time + datetime.timedelta(seconds=fraction * total_duration)
            point.time = point_time
        elif skip_map_matching:
            # If skipping map matching, use original timestamp if available
            time_idx = min(i, len(raw_points) - 1)
            point.time = raw_points[time_idx]['time']
        else:
            # Fallback to old method as last resort
            total_original = len(raw_points)
            original_idx = min(int(i * total_original / total_matched), total_original - 1)
            point.time = raw_points[original_idx]['time']
            
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
        track_points.append(point_data)
    
    return gpx_xml, track_points

def parse_gpx_file(gpx_contents, safe_datetime_func):
    """
    Parse GPX file contents and extract track points
    
    Args:
        gpx_contents: String containing GPX XML content
        safe_datetime_func: Function to safely convert datetime objects
        
    Returns:
        list: List of track points as dicts with lat, lon, time
    """
    try:
        gpx = gpxpy.parse(gpx_contents)
        
        # Extract track points
        raw_points = []
        for track in gpx.tracks:
            for segment in track.segments:
                for pt in segment.points:
                    raw_points.append({
                        'lat': pt.latitude,
                        'lon': pt.longitude,
                        'time': safe_datetime_func(pt.time)
                    })
        
        logger.info(f"Extracted {len(raw_points)} points from GPX file")
        return raw_points
    except Exception as e:
        logger.error(f"Error parsing GPX file: {str(e)}")
        return []
