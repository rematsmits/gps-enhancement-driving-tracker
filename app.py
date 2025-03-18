from flask import Flask, request, render_template, send_file, redirect, url_for, jsonify
from io import BytesIO
import json
import logging
from werkzeug.utils import secure_filename
import xml.etree.ElementTree as ET

# Import services
from services.track_processor import prepare_track_for_template, process_gpx_workflow

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # limit upload size (16 MB)
app.config['UPLOAD_FOLDER'] = 'uploads'  # Define the upload folder
# Set up logging
logging.basicConfig(level=logging.INFO)

# Global variables to store last processed track (for simplicity in this demo)
latest_corrected_gpx = None
latest_track_points = None  # list of dicts: [{'lat': ..., 'lon': ..., 'time': ...}, ...]

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

        try:
            # Read GPX file content
            gpx_contents = file.read().decode('utf-8', errors='ignore')
            
            # Process the GPX file through our workflow
            success, message, gpx_xml, track_points, track_data, _ = process_gpx_workflow(
                gpx_contents
            )
            
            if success:
                # Update global variables for download and display
                latest_corrected_gpx = gpx_xml
                latest_track_points = track_points
                
                # Update data for rendering
                track_data_for_template = track_data
                track_json = json.dumps(track_data_for_template, ensure_ascii=False)
            
            # Render response
            return render_template('index.html', 
                                  track=track_data_for_template, 
                                  track_json=track_json,
                                  message=message)
            
        except Exception as e:
            app.logger.error(f"Error processing file: {str(e)}", exc_info=True)
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