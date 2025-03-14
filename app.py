from flask import Flask, request, render_template, send_file, redirect, url_for, jsonify
from io import BytesIO
import requests, json, math, datetime
import gpxpy   # Library for parsing and generating GPX
import logging
from werkzeug.utils import secure_filename
import traceback
import xml.etree.ElementTree as ET

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # limit upload size (16 MB)
app.config['UPLOAD_FOLDER'] = 'uploads'  # Define the upload folder
# Set up logging
logging.basicConfig(level=logging.INFO)

# Global variables to store last processed track (for simplicity in this demo)
latest_corrected_gpx = None
latest_track_points = None  # list of dicts: [{'lat': ..., 'lon': ..., 'time': ...}, ...]

# Convert the track points to a serializable format for the template
def prepare_track_for_template(track_points):
    if not track_points:
        return []  # Return empty array instead of None
        
    result = []
    for pt in track_points:
        point = {
            'lat': pt.get('lat', 0),
            'lon': pt.get('lon', 0)
        }
        
        # Format time as ISO string for JavaScript compatibility if it exists
        if pt.get('time'):
            try:
                point['time'] = format_time_for_js(pt['time'])
            except Exception:
                pass
                
        result.append(point)
        
    return result

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
def interpolate_track(points, max_time_gap=1):  # Reduced from 3 to 1 seconds for denser points
    if not points:
        return points
    interpolated = [points[0]]
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i+1]
        interpolated.append(p1)
        
        # Check if points are too far apart spatially 
        # (approximately 25 meters based on rough conversion from degrees)
        dist = haversine(p1['lat'], p1['lon'], p2['lat'], p2['lon'])
        
        # Also calculate time difference
        t1 = p1['time']
        t2 = p2['time']
        if t2 and t1:
            dt = (t2 - t1).total_seconds()
        else:
            dt = 0
        
        # Interpolate if there's a large spatial gap or time gap
        if dist > 15 or dt > max_time_gap:  # Reduced from 25m to 15m for denser points
            # app.logger.debug(f"Interpolating gap: {dist:.1f}m or {dt:.1f}s between points")
            
            # Decide how many points to insert based on the larger criteria
            # At least 1 point per 15m or per max_time_gap seconds
            num_by_dist = max(1, int(dist // 15))  # Reduced from 25 to 15
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

# Split track into chunks that are under Valhalla's point limit but optimize for road matching
def chunk_track(points, max_chunk_size=15000, overlap=50):
    """Split track into chunks with natural chunk boundaries based on features like pauses and turns"""
    # For very small tracks, don't split
    if len(points) <= max_chunk_size:
        return [points]  # Track is small enough to process in one go
    
    # First, try to find natural break points based on:
    # 1. Pauses in movement (time gaps)
    # 2. Sharp turns or direction changes
    # 3. Speed changes
    
    break_indices = []
    
    # Only analyze inner points (not first/last)
    for i in range(1, len(points) - 1):
        should_break = False
        
        # Check for time gaps (pauses) if time data is available
        if 'time' in points[i] and 'time' in points[i-1] and points[i]['time'] and points[i-1]['time']:
            time_diff = (points[i]['time'] - points[i-1]['time']).total_seconds()
            if time_diff > 60:  # Significant pause (1+ minute)
                should_break = True
        
        # Check for sharp turns by calculating angle change
        if i > 1:
            p1 = points[i-2]
            p2 = points[i-1]
            p3 = points[i]
            
            # Calculate bearing changes
            bearing1 = math.atan2(p2['lon'] - p1['lon'], p2['lat'] - p1['lat'])
            bearing2 = math.atan2(p3['lon'] - p2['lon'], p3['lat'] - p2['lat'])
            
            angle_change = abs(bearing2 - bearing1)
            # Normalize angle to [0, π]
            while angle_change > math.pi:
                angle_change -= 2 * math.pi
            angle_change = abs(angle_change)
            
            if angle_change > math.pi / 4:  # More than 45° turn
                should_break = True
        
        # Add as potential break point if criteria met
        if should_break:
            break_indices.append(i)
    
    # If we found natural break points, use them
    if break_indices:
        # Ensure we don't have break points too close to each other
        filtered_breaks = [0]  # Start with the first point
        min_chunk_size = max_chunk_size // 10  # Minimum chunk size (10% of max)
        
        for idx in sorted(break_indices):
            if idx - filtered_breaks[-1] >= min_chunk_size:
                filtered_breaks.append(idx)
        
        # Add the last point
        if len(points) - 1 - filtered_breaks[-1] >= min_chunk_size:
            filtered_breaks.append(len(points) - 1)
        
        # Create chunks based on natural breaks
        natural_chunks = []
        for i in range(len(filtered_breaks) - 1):
            start_idx = max(0, filtered_breaks[i] - overlap // 2)
            end_idx = min(len(points), filtered_breaks[i+1] + overlap // 2)
            natural_chunks.append(points[start_idx:end_idx])
        
        # If we have a reasonable number of natural chunks, use them
        if len(natural_chunks) >= 2 and all(len(chunk) <= max_chunk_size for chunk in natural_chunks):
            app.logger.info(f"Using {len(natural_chunks)} natural chunks based on track features")
            return natural_chunks
    
    # Fallback: split evenly if natural chunking didn't work well
    app.logger.info("Using standard chunk splitting")
    chunks = []
    start_idx = 0
    
    while start_idx < len(points):
        # Calculate end index for this chunk (including overlap)
        end_idx = min(start_idx + max_chunk_size, len(points))
        
        # Extract chunk
        chunk = points[start_idx:end_idx]
        chunks.append(chunk)
        
        # Move to next chunk start, with overlap for better stitching
        start_idx = end_idx - overlap if end_idx < len(points) else len(points)
    
    return chunks

# Decode polyline from Valhalla response
def decode_polyline(encoded):
    coords = []
    index = 0
    lat = 0
    lon = 0
    while index < len(encoded):
        result = 1
        shift = 0
        b = 0
        # latitude
        while True:
            b = ord(encoded[index]) - 63 - 1
            index += 1
            result += b << shift
            shift += 5
            if b < 0x1f:
                break
        lat += ~(result >> 1) if (result & 1) else (result >> 1)
        result = 1
        shift = 0
        # longitude
        while True:
            b = ord(encoded[index]) - 63 - 1
            index += 1
            result += b << shift
            shift += 5
            if b < 0x1f:
                break
        lon += ~(result >> 1) if (result & 1) else (result >> 1)
        coords.append((lat * 1e-6, lon * 1e-6))
    return coords

# Process a single chunk with Valhalla
def process_chunk_with_valhalla(chunk):
    """Process a single chunk with Valhalla with enhanced leg extraction"""
    # Prepare shape for Valhalla
    shape = [{
        "lat": p["lat"], 
        "lon": p["lon"], 
        "time": format_time_for_js(p["time"]) if "time" in p else None
    } for p in chunk]
    
    # Use trace_attributes endpoint instead of trace_route for more precise matching
    valhalla_url = "http://valhalla:8002/trace_attributes"
    
    # Enhanced request payload specifically requesting shape
    request_payload = {
        "costing": "auto",
        "shape_match": "map_snap",  # Using map_snap for best results
        "shape": shape,
        "filters": {
            "attributes": ["shape", "edge.way_id", "edge.names", "edge.id", "edge.weighted_grade", 
                          "matched_point.type", "matched_point.edge_index"],
            "action": "include"
        },
        "costing_options": {
            "auto": {
                "search_radius": 100,  # Increased from 50 for better road matching in rural areas
                "turn_penalty_factor": 50,  # Reduced from 100 to allow more natural routes
                "service_penalty": 0,
                "shortest": False  # Changed to false for more realistic routes
            }
        },
        "trace_options": {
            "search_radius": 100,  # Increased from 50 to find roads in sparse areas
            "gps_accuracy": 3.0,  # Reduced from 5.0 for more precise matching
            "interpolation_distance": 0.5,  # Reduced for higher density
            "max_route_distance_factor": 3,  # Reduced for more precise matching
            "max_route_time_factor": 3,
            "breakage_distance": 500,  # Reduced from 2000 to avoid long jumps
            "max_search_radius": 200,  # Increased from 50 to find roads in sparse areas
            "filter_action": "include",  # Ensure we include all points
            "use_timestamps": True  # Use time information if available
        }
    }
    
    try:
        # Make the request
        headers = {"Content-Type": "application/json"}
        res = requests.post(valhalla_url, json=request_payload, headers=headers, timeout=180)
        
        if res.status_code != 200:
            app.logger.error(f"Valhalla error: {res.text}")
            return None
        
        # Parse response
        data = res.json()
        app.logger.info(f"Response keys: {list(data.keys())}")
        
        # Extract the matched points from trace_attributes response
        if "matched_points" in data:
            matched_points = data["matched_points"]
            app.logger.info(f"Found {len(matched_points)} matched points")
            
            # Extract coordinates from matched points
            matched_coords = []
            for point in matched_points:
                if "lat" in point and "lon" in point:
                    matched_coords.append((point["lat"], point["lon"]))
            
            if matched_coords and len(matched_coords) > len(chunk) * 0.3:  # Ensure we got enough matched points
                app.logger.info(f"Extracted {len(matched_coords)} coordinates from matched points")
                return matched_coords
        
        # If no matched_points or too few points, try to get coordinates from shape
        if "shape" in data:
            shape = decode_polyline(data["shape"])
            app.logger.info(f"Using shape with {len(shape)} points")
            
            # Check if shape has enough points
            if len(shape) > 10:
                return shape
            
        # If no shape with enough points, try edges
        if "edges" in data:
            edges = data["edges"]
            app.logger.info(f"Found {len(edges)} edges in response")
            
            # Combine shapes from all edges
            all_points = []
            
            for edge_idx, edge in enumerate(edges):
                if "shape" in edge:
                    edge_shape = decode_polyline(edge["shape"])
                    app.logger.info(f"Edge {edge_idx+1} has {len(edge_shape)} shape points")
                    all_points.extend(edge_shape)
            
            if all_points and len(all_points) > 10:
                app.logger.info(f"Extracted {len(all_points)} points from edges")
                return all_points

        # Fall back to using original points, but don't sample as aggressively
        app.logger.warning("Could not extract route from Valhalla, using original points")
        sample_rate = max(1, len(chunk) // 500)  # Take more points (was 200)
        return [(p["lat"], p["lon"]) for i, p in enumerate(chunk) if i % sample_rate == 0]
        
    except Exception as e:
        app.logger.error(f"Error processing chunk: {str(e)}")
        traceback.print_exc()  # Print full stack trace
        return None

def connect_processed_chunks(chunks):
    """Connect multiple processed chunks into a continuous track with improved connection logic"""
    if not chunks:
        return []
    if len(chunks) == 1:
        return chunks[0]
    
    connected = chunks[0].copy()
    
    for i in range(1, len(chunks)):
        if not chunks[i]:
            continue
            
        # Find best connection point between chunks
        if len(connected) > 10 and len(chunks[i]) > 10:
            # Use more points for matching to find better connections
            last_points = connected[-30:]  # Increased from 15 to 30 for better matching
            first_points = chunks[i][:30]  # Increased from 15 to 30 for better matching
            
            min_dist = float('inf')
            best_prev_idx = -1
            best_new_idx = -1
            
            for j, (lat1, lon1) in enumerate(last_points):
                for k, (lat2, lon2) in enumerate(first_points):
                    dist = haversine(lat1, lon1, lat2, lon2)
                    if dist < min_dist:
                        min_dist = dist
                        best_prev_idx = len(connected) - 30 + j  # Adjusted for new window size
                        best_new_idx = k
            
            # Connect at closest matching point with improved distance threshold
            if min_dist < 30:  # Reduced from 50 to 30 meters for more precision
                connected = connected[:best_prev_idx + 1]
                connected.extend(chunks[i][best_new_idx:])
            else:
                # If no good connection, create a gradual transition between chunks
                # instead of a straight line to prevent spikes
                if min_dist < 300:  # Increased from 200 for more cases
                    p1 = connected[-1]
                    p2 = chunks[i][0]
                    
                    # Add multiple intermediate points instead of just one
                    steps = min(10, max(3, int(min_dist / 30)))
                    for step in range(1, steps):
                        frac = step / steps
                        midpoint = ((p1[0] + frac * (p2[0] - p1[0])), 
                                    (p1[1] + frac * (p2[1] - p1[1])))
                        connected.append(midpoint)
                
                # Skip fewer points from the next chunk to ensure smoother transition
                skip_count = min(2, len(chunks[i]) // 30)
                connected.extend(chunks[i][skip_count:])
        else:
            # Skip fewer points for smoother transitions
            skip_count = min(2, len(chunks[i]) // 30)
            connected.extend(chunks[i][skip_count:])
    
    return connected

def process_track(track, use_map_matching=True):
    """Process a track with smoothing, interpolation and optional map matching"""
    # Apply smoothing and interpolation 
    smoothed = smooth_track(track, window=3)  # Reduced window size from 5 to 3 for less aggressive smoothing
    
    # More aggressive interpolation for denser points
    processed_points = interpolate_track(smoothed, max_time_gap=0.5)  # Reduced from 1 to 0.5 second for even denser points
    
    # If not using map matching, return the processed points as coordinates
    if not use_map_matching:
        return [(p["lat"], p["lon"]) for p in processed_points]
    
    # Determine optimal chunk size based on track length
    num_points = len(processed_points)
    
    # Use smaller chunks with greater overlap to prevent spikes
    if num_points < 3000:
        max_chunk_size = num_points  # Process small tracks as single chunk
        overlap = 0
    elif num_points < 10000:
        max_chunk_size = 3000  # Smaller chunks for medium-sized tracks (reduced from 5000)
        overlap = max(500, max_chunk_size // 5)  # 20% overlap (increased from 10%)
    else:
        max_chunk_size = 5000  # Smaller chunks for large tracks (reduced from 8000)
        overlap = max(800, max_chunk_size // 5)  # 20% overlap (increased from 10%)
    
    app.logger.info(f"Processing track with {num_points} points, chunk size {max_chunk_size}, overlap {overlap}")
    
    # Split into chunks and process with Valhalla
    chunks = chunk_track(processed_points, max_chunk_size, overlap)
    app.logger.info(f"Split track into {len(chunks)} chunks")
    
    processed_chunks = []
    
    for i, chunk in enumerate(chunks):
        app.logger.info(f"Processing chunk {i+1}/{len(chunks)} with {len(chunk)} points")
        matched_coords = process_chunk_with_valhalla(chunk)
        
        if matched_coords and len(matched_coords) >= 5:
            app.logger.info(f"Successfully processed chunk {i+1} with {len(matched_coords)} points")
            processed_chunks.append(matched_coords)
        else:
            app.logger.warning(f"Failed to process chunk {i+1}, will try again with smaller pieces")
            
            # If a chunk fails, try to process it as smaller sub-chunks
            if len(chunk) > 1000:
                sub_chunk_size = min(1000, len(chunk) // 2)
                sub_overlap = sub_chunk_size // 5
                sub_chunks = chunk_track(chunk, sub_chunk_size, sub_overlap)
                
                for sub_chunk in sub_chunks:
                    sub_matched = process_chunk_with_valhalla(sub_chunk)
                    if sub_matched and len(sub_matched) >= 5:
                        processed_chunks.append(sub_matched)
    
    # Connect the processed chunks
    matched_track = connect_processed_chunks(processed_chunks)
    
    # Check for any remaining spikes (straight lines longer than 100m)
    if matched_track and len(matched_track) > 5:
        spike_free_track = []
        for i in range(len(matched_track) - 1):
            p1 = matched_track[i]
            p2 = matched_track[i + 1]
            spike_free_track.append(p1)
            
            # Check for long straight lines that could be spikes
            dist = haversine(p1[0], p1[1], p2[0], p2[1])
            
            # More aggressive detection of straight lines
            if dist > 100:  # Reduced from 300m to 100m to catch more spikes
                app.logger.info(f"Found potential spike: {dist:.1f}m between points")
                
                # Add more points to break up the spike
                steps = max(5, int(dist / 20))  # Increased from 3 to 5 steps minimum, 100m to 20m per step
                
                # Check if we can use nearby points instead of linear interpolation
                nearby_points = []
                search_radius = min(dist / 2, 500)  # Search up to half the spike distance or 500m max
                
                for j in range(max(0, i-10), min(len(matched_track), i+10)):
                    if j != i and j != i+1:  # Skip the current points (spike endpoints)
                        p_test = matched_track[j]
                        # Check if this point is close to the spike line
                        mid_lat = (p1[0] + p2[0]) / 2
                        mid_lon = (p1[1] + p2[1]) / 2
                        if haversine(p_test[0], p_test[1], mid_lat, mid_lon) < search_radius:
                            nearby_points.append(p_test)
                
                if nearby_points:
                    # If we found nearby points, use them to create a more natural path
                    app.logger.info(f"Found {len(nearby_points)} nearby points to replace spike")
                    # Sort by distance from start point
                    nearby_points.sort(key=lambda p: haversine(p[0], p[1], p1[0], p1[1]))
                    for np in nearby_points:
                        spike_free_track.append(np)
                else:
                    # Otherwise use denser linear interpolation
                    for j in range(1, steps):
                        frac = j / steps
                        mid_lat = p1[0] + frac * (p2[0] - p1[0])
                        mid_lon = p1[1] + frac * (p2[1] - p1[1])
                        spike_free_track.append((mid_lat, mid_lon))
            

        # Add the last point
        if matched_track:
            spike_free_track.append(matched_track[-1])
        
        matched_track = spike_free_track
    
    # Add interpolation if too few points were returned
    if matched_track and (len(matched_track) < 300 or len(matched_track) < num_points * 0.2):  # Changed threshold from 200 to 300 points and 10% to 20%
        # Calculate average distance between points for adaptive interpolation
        total_dist = 0
        count = 0
        for i in range(len(matched_track) - 1):
            lat1, lon1 = matched_track[i]
            lat2, lon2 = matched_track[i+1]
            dist = haversine(lat1, lon1, lat2, lon2)
            if dist > 0:
                total_dist += dist
                count += 1
        
        avg_dist = total_dist / max(1, count) if count > 0 else 20
        target_dist = min(3, max(0.5, avg_dist / 5))  # More aggressive target distance
        
        # Interpolate to ensure consistent point density
        interpolated_matched_track = []
        for i in range(len(matched_track) - 1):
            lat1, lon1 = matched_track[i]
            lat2, lon2 = matched_track[i+1]
            dist = haversine(lat1, lon1, lat2, lon2)
            
            interpolated_matched_track.append((lat1, lon1))
            
            if dist > target_dist * 1.1:  # Reduced threshold
                num_points = max(1, int(dist / target_dist) - 1)
                for j in range(1, num_points + 1):
                    frac = j / (num_points + 1)
                    new_lat = lat1 + frac * (lat2 - lat1)
                    new_lon = lon1 + frac * (lon2 - lon1)
                    interpolated_matched_track.append((new_lat, new_lon))
        
        # Add the last point
        if matched_track:
            interpolated_matched_track.append(matched_track[-1])
        
        return interpolated_matched_track
    
    return matched_track

@app.route('/', methods=['GET', 'POST'])
def index():
    """Main route for web interface"""
    global latest_corrected_gpx, latest_track_points
    
    track_data_for_template = prepare_track_for_template(latest_track_points)
    track_json = json.dumps(track_data_for_template, ensure_ascii=False)
    
    if request.method == 'POST':
        # Handle file upload
        file = request.files.get('gpx_file')
        if not file or file.filename == '':
            return render_template('index.html', 
                                  track=track_data_for_template,
                                  track_json=track_json,
                                  message="No file selected.")
        
        # Check if map matching should be skipped
        skip_map_matching = 'skip_map_matching' in request.form
        
        try:
            # Parse uploaded GPX
            gpx_contents = file.read().decode('utf-8', errors='ignore')
            gpx = gpxpy.parse(gpx_contents)
            
            # Extract track points
            raw_points = []
            for track in gpx.tracks:
                for segment in track.segments:
                    for pt in segment.points:
                        raw_points.append({
                            'lat': pt.latitude,
                            'lon': pt.longitude,
                            'time': safe_datetime(pt.time)
                        })
            
            if not raw_points:
                return render_template('index.html', 
                                      track=track_data_for_template,
                                      track_json=track_json,
                                      message="No track points found in GPX.")
            
            # Process track
            matched_coords = process_track(raw_points, use_map_matching=not skip_map_matching)
            
            if not matched_coords:
                return render_template('index.html', 
                                      track=track_data_for_template,
                                      track_json=track_json,
                                      message="Processing failed. Try the 'Skip map matching' option.")
            
            # Build corrected GPX
            gpx_out = gpxpy.gpx.GPX()
            gpx_track = gpxpy.gpx.GPXTrack()
            gpx_out.tracks.append(gpx_track)
            seg = gpxpy.gpx.GPXTrackSegment()
            gpx_track.segments.append(seg)
            
            # Distribute times across matched points
            total_matched = len(matched_coords)
            total_original = len(raw_points)
            
            for i, (lat, lon) in enumerate(matched_coords):
                # Get time from original points
                if skip_map_matching:
                    time = raw_points[min(i, total_original-1)]['time']
                else:
                    original_idx = min(int(i * total_original / total_matched), total_original - 1)
                    time = raw_points[original_idx]['time']
                
                # Create GPX point
                point = gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lon)
                if time:
                    point.time = time
                seg.points.append(point)
            
            # Store for download
            latest_corrected_gpx = gpx_out.to_xml()
            
            # Store track points for display
            latest_track_points = []
            for pt in seg.points:
                point_data = {
                    'lat': pt.latitude, 
                    'lon': pt.longitude
                }
                if pt.time:
                    point_data['time'] = format_time_for_js(pt.time)
                latest_track_points.append(point_data)
            
            # Update template data
            track_data_for_template = prepare_track_for_template(latest_track_points)
            track_json = json.dumps(track_data_for_template, ensure_ascii=False)
            
            # Add message about which processing mode was used
            mode_message = "Original GPS data" if skip_map_matching else "Map-matched data"
                
            return render_template('index.html', 
                                  track=track_data_for_template, 
                                  track_json=track_json,
                                  message=f"Track processed successfully! Using {mode_message}.")
            
        except Exception as e:
            return render_template('index.html', 
                                  track=track_data_for_template,
                                  track_json=track_json,
                                  message=f"Error processing file: {str(e)}")
    
    # GET request - show upload form or map if already processed
    return render_template('index.html', 
                          track=track_data_for_template,
                          track_json=track_json)
        
@app.route('/download')
def download():
    """Download the corrected GPX file"""
    global latest_corrected_gpx
    if latest_corrected_gpx is None:
        # If no file processed yet, redirect to home
        return redirect(url_for('index'))
    # Send the GPX content as a file download
    return send_file(BytesIO(latest_corrected_gpx.encode('utf-8')), 
                     mimetype='application/gpx+xml',
                     as_attachment=True, download_name="corrected_track.gpx")
