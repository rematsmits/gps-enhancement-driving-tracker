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
    
    # Find nearest points and assign more accurate timing
    if skip_map_matching:
        # When skip_map_matching is true, use original points directly, which preserves high-speed segments
        for i, (lat, lon) in enumerate(matched_coords):
            point = gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lon)
            
            # Map directly to raw points index if possible
            if i < len(raw_points):
                point.time = raw_points[i]['time']
            else:
                # Fallback if indices don't match
                time_idx = min(i, len(raw_points) - 1)
                point.time = raw_points[time_idx]['time']
                
            seg.points.append(point)
    else:
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
            p1 = matched_coords[i-1]
            p2 = matched_coords[i]
            d = ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5  # Simple distance
            total_dist_matched += d
            distances_matched.append(total_dist_matched)
        
        # Now assign times based on relative distances
        for i, (lat, lon) in enumerate(matched_coords):
            point = gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lon)
            
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
