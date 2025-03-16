import datetime
import math

# Format datetime object as ISO string for JavaScript
def format_time_for_js(dt):
    """Convert datetime to ISO string for JavaScript"""
    if dt is None:
        return None
    try:
        return dt.isoformat() if not isinstance(dt, str) else dt
    except Exception:
        return None

# Safely handle datetime objects with timezone information
def safe_datetime(dt):
    """Convert datetime to UTC or return None if invalid"""
    if dt is None:
        return None
        
    try:
        return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None

# Haversine formula for distance between two lat/lon points (in meters)
def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two lat/lon points in meters using Haversine formula"""
    # Earth radius in meters
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(d_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# Simple moving-average smoothing for a sequence of latitude/longitude points
def smooth_track(points, window=5):
    """Apply a moving average smoothing filter to a track"""
    if window < 3 or len(points) < window:
        return points  # not enough points to smooth
    
    smoothed = []
    n = len(points)
    half = window // 2
    
    for i in range(n):
        if i < half or i > n-half-1:
            # For the edges, just copy original
            smoothed.append(points[i])
        else:
            # Average over [i-half, ..., i+half]
            lat_sum = lon_sum = 0.0
            for j in range(i-half, i+half+1):
                lat_sum += points[j]['lat']
                lon_sum += points[j]['lon']
            avg_lat = lat_sum / (window)
            avg_lon = lon_sum / (window)
            smoothed.append({'lat': avg_lat, 'lon': avg_lon, 'time': points[i]['time']})
    
    return smoothed

# Linear interpolation to insert additional points if gaps are large
def interpolate_track(points, max_time_gap=1):
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
        if dist > 15 or dt > max_time_gap:
            # Decide how many points to insert based on the larger criteria
            num_by_dist = max(1, int(dist // 15))
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
