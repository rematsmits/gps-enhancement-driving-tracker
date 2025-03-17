import datetime
from functions.haversine import haversine
from functions.safe_datetime import safe_datetime
from functions.js_date_format import format_time_for_js

# Linear interpolation to insert additional points if gaps are large
def interpolate_track(points, max_time_gap=0.1, max_dist=0.5):
    """Add interpolated points between existing points if gaps are too large (spatially or temporally)"""
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
            # Decide how many points to insert based on the larger criteria
            num_by_dist = max(1, int(dist // max_dist))
            num_by_time = max(1, int(dt // max_time_gap))
            num_new = max(num_by_dist, num_by_time)
            
            for k in range(1, num_new+1):
                frac = k / float(num_new+1)
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
