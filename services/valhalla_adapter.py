import logging
import requests
import traceback
from functions.js_date_format import format_time_for_js

# Configure logging
logger = logging.getLogger(__name__)

# Decode polyline from Valhalla response
def decode_polyline(encoded):
    """Decode a Valhalla polyline to a list of lat/lon coordinates as dictionaries"""
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
        coords.append({'lat': lat * 1e-6, 'lon': lon * 1e-6})
    return coords

# Process a single chunk with Valhalla
def process_chunk_with_valhalla(chunk, valhalla_url="http://valhalla:8002/trace_attributes"):
    """Process a single chunk with Valhalla map matching service"""
    # Prepare shape for Valhalla
    shape = [{
        "lat": p["lat"], 
        "lon": p["lon"], 
        "time": format_time_for_js(p["time"]) if "time" in p else None
    } for p in chunk]
    
    # Enhanced request payload specifically requesting shape
    request_payload = {
        "costing": "auto",
        "shape_match": "map_snap",  # Changed from map_snap to map_match for stricter road adherence
        "shape": shape,
        "filters": {
            "attributes": ["shape", "edge.way_id", "edge.names", "edge.id", "edge.weighted_grade", "edge.surface"],
            "action": "include"
        },
        "costing_options": {
            "auto": {
                "search_radius": 100,  # Increased further to find proper roads
                "turn_penalty_factor": 100,  # Dramatically increased to heavily penalize sharp turns
                "shortest": False,  # Essential to avoid shortcuts
                "max_distance": 100,  # Limit max distance considered
                # Added options to avoid unpaved/country roads
                "use_highways": 1.0,  # Maximum preference for highways (0.0-1.0)
                "use_tolls": 1.0,     # Allow toll roads without penalty
                "use_trails": 0.0,    # Avoid trails completely (0.0-1.0)
                "exclude_unpaved": True,  # Explicitly exclude unpaved roads when possible
                # Surface type penalties - higher values avoid these surfaces
                "surface_factor": 0.7,  # Factor that penalizes roads based on surface type
                # Hierarchy factor - higher value (0-1) prefers higher-class roads
                "hierarchy_factor": 0.8  # Strongly prefer major roads over minor ones
            }
        },
        "trace_options": {
            "search_radius": 100,  # Increased search radius
            "gps_accuracy": 3.0,  # Reduced further to trust road network more than GPS points
            "interpolation_distance": 10,  # Increased for smoother path
            "max_route_distance_factor": 10,  # Allow reasonable route distances
            "max_route_time_factor": 10,
            "breakage_distance": 2000,  # Increased to avoid track fragmentation
            "max_search_radius": 250,  # Increased to find better roads
            "filter_action": "include",
            "use_timestamps": True
        }
    }
    
    try:
        # Make the request
        headers = {"Content-Type": "application/json"}
        logger.info(f"Sending request to Valhalla with {len(shape)} points")
        
        # Log a sample of the payload for debugging
        logger.debug(f"Request shape_match: {request_payload['shape_match']}")
        logger.debug(f"Request filters: {request_payload['filters']}")
        
        res = requests.post(valhalla_url, json=request_payload, headers=headers, timeout=300)
        
        if res.status_code != 200:
            logger.error(f"Valhalla error: {res.status_code} - {res.text}")
            # If the server is unavailable, return original points rather than failing
            if res.status_code in [502, 503, 504]:
                logger.warning("Valhalla server unavailable, using original points")
                return chunk  # Return original chunk with all data preserved
            return None
        
        # Parse response
        try:
            data = res.json()
        except ValueError as e:
            logger.error(f"Failed to parse Valhalla response: {str(e)}")
            logger.debug(f"Response content: {res.text[:200]}...")  # Log first 200 chars
            return chunk  # Return original chunk with all data preserved
            
        logger.info(f"Response keys: {list(data.keys())}")
        
        # If response contains any warnings, log them
        if "warnings" in data:
            logger.warning(f"Valhalla warnings: {data['warnings']}")
            
        # If there are any error messages, log them
        if "error_message" in data:
            logger.error(f"Valhalla error message: {data['error_message']}")
            if "error" in data:
                logger.error(f"Valhalla error code: {data['error']}")
            return chunk  # Return original chunk with all data preserved
        
        # Extract the matched points from trace_attributes response
        if "matched_points" in data:
            matched_points = data["matched_points"]
            logger.info(f"Found {len(matched_points)} matched points")
            
            # Extract coordinates from matched points as dictionaries
            matched_coords = []
            for i, point in enumerate(matched_points):
                if "lat" in point and "lon" in point:
                    # Create a dictionary with lat/lon and preserve time and speed from original point if available
                    new_point = {"lat": point["lat"], "lon": point["lon"]}
                    
                    # If we have original points with the same array length, preserve time and speed
                    if i < len(chunk):
                        if 'time' in chunk[i]:
                            new_point['time'] = chunk[i]['time']
                        if 'speed' in chunk[i]:
                            new_point['speed'] = chunk[i]['speed']
                    
                    matched_coords.append(new_point)
            
            if matched_coords and len(matched_coords) > len(chunk) * 0.3:  # Ensure we got enough matched points
                logger.info(f"Extracted {len(matched_coords)} coordinates from matched points")
                return matched_coords
        
        # If no matched_points or too few points, try to get coordinates from shape
        if "shape" in data:
            shape = decode_polyline(data["shape"])
            logger.info(f"Using shape with {len(shape)} points")
            
            # Check if shape has enough points
            if len(shape) > 10:
                # Try to transfer time and speed data from original points where possible
                # This is more challenging because the shape may not match 1:1 with original points
                return shape
            
        # If no shape with enough points, try edges
        if "edges" in data:
            edges = data["edges"]
            logger.info(f"Found {len(edges)} edges in response")
            
            # Combine shapes from all edges
            all_points = []
            
            for edge_idx, edge in enumerate(edges):
                if "shape" in edge:
                    edge_shape = decode_polyline(edge["shape"])
                    logger.info(f"Edge {edge_idx+1} has {len(edge_shape)} shape points")
                    all_points.extend(edge_shape)
            
            if all_points and len(all_points) > 10:
                logger.info(f"Extracted {len(all_points)} points from edges")
                return all_points

        # Fall back to using original points, preserving all data
        logger.warning("Could not extract route from Valhalla, using original points")
        return chunk
        
    except Exception as e:
        logger.error(f"Error processing chunk: {str(e)}")
        traceback.print_exc()  # Print full stack trace
        return None
