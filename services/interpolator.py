import datetime
import math
from functions.haversine import haversine

# Linear interpolation to insert additional points if gaps are large
def interpolate_track(points, max_time_gap=0.05, max_dist=0.05):
    """
    Add interpolated points between existing points if gaps are too large (spatially or temporally)
    
    :param points: The list of track points to interpolate
    :param max_time_gap: Maximum time gap between points in seconds before inserting additional points
    :param max_dist: Maximum distance gap between points in km before inserting additional points
    :param default_speed: Default speed (km/h) to use if no speed information is available
    :param speed_strategy: Strategy for handling missing speeds:
        - 'auto': Use available speeds, then average speed, then default
        - 'average': Use average speed of track for missing values
        - 'default': Use the specified default_speed (or internal default)
        - 'none': Skip interpolation if no speed data is available
    :return: The interpolated track with additional points
    """
    if not points:
        return points
        
    interpolated = [points[0]]
    
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i+1]
        interpolated.append(p1)
        
        # Check if points are too far apart spatially
        dist = haversine(p1['lat'], p1['lon'], p2['lat'], p2['lon'])
        
        # Also calculate time difference
        t1 = p1['time']
        t2 = p2['time']
        if t2 and t1:
            dt = (t2 - t1).total_seconds()
        else:
            dt = 0
        
        # Interpolate if there's a large spatial gap or time gap
        if dist > max_dist or dt > max_time_gap:
            # Calculate the number of segments needed to maintain even distribution
            # Use ceiling to ensure we don't exceed max_dist or max_time_gap
            num_segments_by_dist = math.ceil(dist / max_dist) if max_dist > 0 else 1
            num_segments_by_time = math.ceil(dt / max_time_gap) if max_time_gap > 0 else 1
            
            # Use the more constraining factor (whichever requires more points)
            num_segments = max(num_segments_by_dist, num_segments_by_time)
            
            # Number of new points to insert = segments - 1
            num_new_points = num_segments - 1
            
            # Insert evenly spaced points
            for k in range(1, num_new_points + 1):
                # Calculate the exact fraction for even spacing
                frac = k / float(num_segments)
                new_lat = p1['lat'] + frac * (p2['lat'] - p1['lat'])
                new_lon = p1['lon'] + frac * (p2['lon'] - p1['lon'])
                
                # interpolate time
                if t1 and t2:
                    new_time = t1 + datetime.timedelta(seconds=frac * dt)
                else:
                    new_time = None
                    
                interpolated.append({'lat': new_lat, 'lon': new_lon, 'time': new_time})
    
    interpolated.append(points[-1])
    return interpolated
