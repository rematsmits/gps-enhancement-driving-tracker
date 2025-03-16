import logging
from services.interpolator import smooth_track, interpolate_track, format_time_for_js
from services.track_chunks_processor import chunk_track, connect_processed_chunks
from services.valhalla_adapter import process_chunk_with_valhalla
from services.gpx_processor import build_gpx_from_coords, parse_gpx_file

# Configure logging
logger = logging.getLogger(__name__)

def prepare_track_for_template(track_points):
    """Convert track points to a serializable format for the template"""
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

def process_track(track, use_map_matching=True):
    """Process a track with smoothing, interpolation and optional map matching"""
    # Apply smoothing and interpolation 
    smoothed = smooth_track(track, window=3)
    
    # More aggressive interpolation for denser points
    processed_points = interpolate_track(smoothed, max_time_gap=0.5)
    
    # If not using map matching, return the processed points as coordinates
    if not use_map_matching:
        return [(p["lat"], p["lon"]) for p in processed_points]
    
    # Split into chunks and process with Valhalla
    chunks = chunk_track(processed_points)
    
    processed_chunks = []
    
    for i, chunk in enumerate(chunks):
        logger.info(f"Processing chunk {i+1}/{len(chunks)} with {len(chunk)} points")
        matched_coords = process_chunk_with_valhalla(chunk)

        if matched_coords and len(matched_coords) >= 5:
            logger.info(f"Successfully processed chunk {i+1} with {len(matched_coords)} points")
            processed_chunks.append(matched_coords)
        else:
            logger.warning(f"Failed to process chunk {i+1}, will try again with smaller pieces")
            
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
    
    return matched_track

def process_gpx_workflow(gpx_contents, safe_datetime_func, skip_map_matching=False):
    """
    Complete workflow for processing a GPX file
    
    Args:
        gpx_contents: String containing GPX file contents
        safe_datetime_func: Function to safely handle datetime objects
        skip_map_matching: Whether to skip map matching
        
    Returns:
        tuple: (success, message, gpx_xml, track_points, track_data_for_template, track_json)
            - success: Boolean indicating if processing was successful
            - message: Status message for the user
            - gpx_xml: Generated GPX XML string for download
            - track_points: List of processed track points
            - track_data_for_template: Formatted track data for the template
            - track_json: JSON string of track data for the UI
    """
    try:
        # Parse the GPX file
        raw_points = parse_gpx_file(gpx_contents, safe_datetime_func)
        
        if not raw_points:
            return False, "No track points found in GPX.", None, None, [], "{}"
        
        # Process the track
        matched_coords = process_track(raw_points, use_map_matching=not skip_map_matching)
        
        if not matched_coords:
            return False, "Processing failed. Try the 'Skip map matching' option.", None, None, [], "{}"
        
        # Build GPX from processed coordinates
        gpx_xml, track_points = build_gpx_from_coords(
            matched_coords, raw_points, skip_map_matching
        )
        
        # Prepare data for template
        track_data = prepare_track_for_template(track_points)
        
        # Determine success message
        mode_message = "Original GPS data" if skip_map_matching else "Map-matched data"
        success_message = f"Track processed successfully! Using {mode_message}."
        
        # Return all needed data
        return True, success_message, gpx_xml, track_points, track_data, None
        
    except Exception as e:
        logger.error(f"Error in GPX processing workflow: {str(e)}", exc_info=True)
        return False, f"Error processing file: {str(e)}", None, None, [], "{}"