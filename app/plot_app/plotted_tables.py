""" methods to generate various tables used in configured_plots.py """
import os
from html import escape
from math import sqrt
import datetime
import pytz
import numpy as np
import csv
from bokeh.layouts import column
from bokeh.models import ColumnDataSource
from bokeh.models.widgets import DataTable, TableColumn, Div, HTMLTemplateFormatter

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from config import plot_color_red, get_kml_filepath
from helper import (
    get_default_parameters, get_airframe_name,
    get_total_flight_time, error_labels_table
    )
from events import get_logged_events


#pylint: disable=consider-using-enumerate,too-many-statements

csv_table_data = {}

def _get_vtol_means_per_mode(vtol_states, timestamps, data):
    """
    get the mean values separated by MC and FW mode for some
    data vector
    :return: tuple of (mean mc, mean fw, max_mc, max_fw)
    """
    vtol_state_index = 0
    current_vtol_state = -1
    sum_mc = 0
    counter_mc = 0
    sum_fw = 0
    counter_fw = 0
    max_mc = 0
    max_fw = 0
    for i in range(len(timestamps)):
        if timestamps[i] > vtol_states[vtol_state_index][0]:
            current_vtol_state = vtol_states[vtol_state_index][1]
            vtol_state_index += 1
        if current_vtol_state == 2: # FW
            sum_fw += data[i]
            counter_fw += 1
            if data[i] > max_fw:
                max_fw = data[i]
        elif current_vtol_state == 3: # MC
            sum_mc += data[i]
            counter_mc += 1
            if data[i] > max_mc:
                max_mc = data[i]
    mean_mc = None
    if counter_mc > 0: 
        mean_mc = sum_mc / counter_mc
        max_mc = max_mc
    mean_fw = None
    if counter_fw > 0: 
        mean_fw = sum_fw / counter_fw
        max_fw = max_fw
    return (mean_mc, mean_fw, max_mc, max_fw)

def get_heading_html(ulog, px4_ulog, db_data, link_to_3d_page,
                     additional_links=None, title_suffix=''):
    """
    Get the html (as string) for the heading information (plots title)
    :param additional_links: list of (label, link) tuples
    """
    sys_name = ''
    if 'sys_name' in ulog.msg_info_dict:
        sys_name = escape(ulog.msg_info_dict['sys_name']) + ' '

    if link_to_3d_page is not None and \
        any(elem.name == 'vehicle_gps_position' for elem in ulog.data_list):
        link_to_3d = ("<a class='btn btn-outline-primary' href='"+
                      link_to_3d_page+"'>Open 3D View</a>")
    else:
        link_to_3d = ''

    added_links = ''
    if additional_links is not None:
        for label, link in additional_links:
            added_links += ("<a class='btn btn-outline-primary' href='"+
                            link+"'>"+label+"</a>")

    if title_suffix != '': title_suffix = ' - ' + title_suffix

    title_html = ("<table width='100%'><tr><td><h3>"+sys_name + px4_ulog.get_mav_type()+
                  title_suffix+"</h3></td><td align='right'>" + link_to_3d +
                  added_links+"</td></tr></table>")
    if db_data.description != '':
        title_html += "<h5>"+db_data.description+"</h5>"
    return title_html

def get_info_table_html(ulog, px4_ulog, db_data, vehicle_data, vtol_states):
    """
    Get the html (as string) for a table with additional text info,
    such as logging duration, max speed etc.
    """

    ### Setup the text for the left table with various information ###
    table_text_left = []

    # airframe
    airframe_name_tuple = get_airframe_name(ulog, True)
    if airframe_name_tuple is not None:
        airframe_name, airframe_id = airframe_name_tuple
        if len(airframe_name) == 0:
            table_text_left.append(('Airframe', airframe_id))

        else:
            table_text_left.append(('Airframe', airframe_name+' <small>('+airframe_id+')</small>'))
        if '<br>' in airframe_name:
            cleaned_airframe_name = airframe_name.replace('<br>', ', ')
        else:
            cleaned_airframe_name = airframe_name
        csv_table_data['Airframe'] = cleaned_airframe_name
        csv_table_data['Airframe ID'] = airframe_id

    table_text_left.append(('', '')) # spacing

    # HW & SW
    sys_hardware = ''
    if 'ver_hw' in ulog.msg_info_dict:
        sys_hardware = escape(ulog.msg_info_dict['ver_hw'])
        if 'ver_hw_subtype' in ulog.msg_info_dict:
            sys_hardware += ' (' + escape(ulog.msg_info_dict['ver_hw_subtype']) + ')'
        table_text_left.append(('Hardware', sys_hardware))
        csv_table_data['Hardware'] = sys_hardware

    release_str = ulog.get_version_info_str()
    if release_str is None:
        release_str = ''
        release_str_suffix = ''
    else:
        release_str += ' <small>('
        release_str_suffix = ')</small>'
    branch_info = ''
    branch_name = ''
    if 'ver_sw_branch' in ulog.msg_info_dict:
        branch_name = ulog.msg_info_dict['ver_sw_branch']
        branch_info = '<br> branch: '+ branch_name
    if 'ver_sw' in ulog.msg_info_dict:
        ver_sw = escape(ulog.msg_info_dict['ver_sw'])
        ver_sw_link = 'https://github.com/PX4/Firmware/commit/'+ver_sw
        ver_sw_result = release_str +'<a href="'+ver_sw_link+'" target="_blank">'+ver_sw[:8]+'</a>'+release_str_suffix+branch_info
        ver_sw_saved_result = ver_sw[:8] + ', ' + branch_name
        table_text_left.append(('Software Version', ver_sw_result))
        csv_table_data['Software Version'] = ver_sw_saved_result

    if 'sys_os_name' in ulog.msg_info_dict and 'sys_os_ver_release' in ulog.msg_info_dict:
        os_name = escape(ulog.msg_info_dict['sys_os_name'])
        os_ver = ulog.get_version_info_str('sys_os_ver_release')
        if os_ver is not None:
            os_fullname_result = os_name + ', ' + os_ver
            table_text_left.append(('OS Version', os_fullname_result))
            csv_table_data['OS Version'] = os_fullname_result

    table_text_left.append(('Estimator', px4_ulog.get_estimator()))
    csv_table_data['Estimator'] = px4_ulog.get_estimator()

    table_text_left.append(('', '')) # spacing

    # logging start time & date
    try:
        # get the first non-zero timestamp
        gps_data = ulog.get_dataset('vehicle_gps_position')
        indices = np.nonzero(gps_data.data['time_utc_usec'])
        if len(indices[0]) > 0:
            # we use the timestamp from the log and then convert it with JS to
            # display with local timezone.
            # In addition we add a tooltip to show the timezone from the log
            logging_start_time = int(gps_data.data['time_utc_usec'][indices[0][0]] / 1000000)

            utc_offset_min = ulog.initial_parameters.get('SDLOG_UTC_OFFSET', 0)
            utctimestamp = datetime.datetime.utcfromtimestamp(
                logging_start_time+utc_offset_min*60).replace(tzinfo=datetime.timezone.utc)

            tooltip = '''This is your local timezone.
<br />
Log timezone: {}
<br />
SDLOG_UTC_OFFSET: {}'''.format(utctimestamp.strftime('%d-%m-%Y %H:%M'), utc_offset_min)
            tooltip = 'data-toggle="tooltip" data-delay=\'{"show":0, "hide":100}\' '+ \
                'title="'+tooltip+'" '
            logging_start_result = '<span style="display:none" id="logging-start-element">'+ str(logging_start_time)+'</span>'
            # table_text_left.append(
            #     ('Logging Start '+
            #      '<i '+tooltip+' class="fa-solid fa-question" aria-hidden="true" '+
            #      'style="color:#666"></i>',
            #      '<span style="display:none" id="logging-start-element">'+
            #      str(logging_start_time)+'</span>'))
            table_text_left.append(
                ('Logging Start '+
                 '<i '+tooltip+' class="fa-solid fa-question" aria-hidden="true" '+
                 'style="color:#666"></i>',logging_start_result))
            
            # Convert the logging start time to UTC datetime object
            logging_start_datetime_utc = datetime.datetime.utcfromtimestamp(logging_start_time)

            # Apply the UTC offset using pytz
            utc_timezone = pytz.timezone('UTC')
            logging_start_datetime_local = utc_timezone.localize(logging_start_datetime_utc) + datetime.timedelta(minutes=utc_offset_min)

            # Convert to local timezone
            local_timezone = pytz.timezone('Asia/Bangkok')
            logging_start_datetime_local = logging_start_datetime_local.astimezone(local_timezone)

            # Format the local time as a string
            logging_start_formatted = logging_start_datetime_local.strftime('%d-%m-%Y %H:%M')
            
            csv_table_data['Logging Start'] = logging_start_formatted
    except:
        # Ignore. Eg. if topic not found
        pass

    # logging duration
    m, s = divmod(int((ulog.last_timestamp - ulog.start_timestamp)/1e6), 60)
    h, m = divmod(m, 60)
    logging_duration_result = '{:d}:{:02d}:{:02d}'.format(h, m, s)
    logging_duration_saved_result = '{:d}:{:02d}:{:02d}'.format(h, m, s)   
    table_text_left.append(('Logging Duration', logging_duration_result))
    csv_table_data['Logging Duration'] = logging_duration_saved_result

    # dropouts
    dropout_durations = [dropout.duration for dropout in ulog.dropouts]
    if len(dropout_durations) > 0:
        total_duration = sum(dropout_durations) / 1000
        if total_duration > 5:
            total_duration_str = '{:.0f}'.format(total_duration)
        else:
            total_duration_str = '{:.2f}'.format(total_duration)
        table_text_left.append(('Dropouts', '{:} ({:} s)'.format(
            len(dropout_durations), total_duration_str)))

    # total vehicle flight time
    flight_time_s = get_total_flight_time(ulog)
    if flight_time_s is not None:
        m, s = divmod(int(flight_time_s), 60)
        h, m = divmod(m, 60)
        days, h = divmod(h, 24)
        flight_time_str = ''
        if days > 0: flight_time_str += '{:d} days '.format(days)
        if h > 0: flight_time_str += '{:d} hours '.format(h)
        if m > 0: flight_time_str += '{:d} minutes '.format(m)
        flight_time_str += '{:d} seconds '.format(s)
        table_text_left.append(('Vehicle Life<br/>Flight Time', flight_time_str))
        csv_table_data['Vehicle Life Flight Time'] = flight_time_str

    table_text_left.append(('', '')) # spacing

    # vehicle UUID (and name if provided). SITL does not have a (valid) UUID
    if 'sys_uuid' in ulog.msg_info_dict and sys_hardware != 'SITL' and \
            sys_hardware != 'PX4_SITL':
        sys_uuid = escape(ulog.msg_info_dict['sys_uuid'])
        if vehicle_data is not None and vehicle_data.name != '':
            sys_uuid = sys_uuid + ' (' + vehicle_data.name + ')'
        if len(sys_uuid) > 0:
            table_text_left.append(('Vehicle UUID', sys_uuid))
            csv_table_data['Vehicle UUID'] = sys_uuid


    table_text_left.append(('', '')) # spacing

    # Wind speed, rating, feedback
    if db_data.wind_speed >= 0:
        table_text_left.append(('Wind Speed', db_data.wind_speed_str()))
    if len(db_data.rating) > 0:
        table_text_left.append(('Flight Rating', db_data.rating_str()))
    if len(db_data.feedback) > 0:
        table_text_left.append(('Feedback', db_data.feedback.replace('\n', '<br/>')))
    if len(db_data.video_url) > 0:
        table_text_left.append(('Video', '<a href="'+db_data.video_url+
                                '" target="_blank">'+db_data.video_url+'</a>'))


    ### Setup the text for the right table: estimated numbers (e.g. max speed) ###
    table_text_right = []
    try:

        local_pos = ulog.get_dataset('vehicle_local_position')
        pos_x = local_pos.data['x']
        pos_y = local_pos.data['y']
        pos_z = local_pos.data['z']
        pos_xyz_valid = np.multiply(local_pos.data['xy_valid'], local_pos.data['z_valid'])
        local_vel_valid_indices = np.argwhere(np.multiply(local_pos.data['v_xy_valid'],
                                                          local_pos.data['v_z_valid']) > 0)
        vel_x = local_pos.data['vx'][local_vel_valid_indices]
        vel_y = local_pos.data['vy'][local_vel_valid_indices]
        vel_z = local_pos.data['vz'][local_vel_valid_indices]

        # total distance (take only valid indexes)
        total_dist_m = 0
        last_index = -2
        for valid_index in np.argwhere(pos_xyz_valid > 0):
            index = valid_index[0]
            if index == last_index + 1:
                dx = pos_x[index] - pos_x[last_index]
                dy = pos_y[index] - pos_y[last_index]
                dz = pos_z[index] - pos_z[last_index]
                total_dist_m += sqrt(dx*dx + dy*dy + dz*dz)
            last_index = index

        if total_dist_m < 1:
            pass # ignore
        elif total_dist_m > 1000:
            table_text_right.append(('Distance', "{:.2f} km".format(total_dist_m/1000)))
            
        else:
            table_text_right.append(('Distance', "{:.2f} m".format(total_dist_m)))
        csv_table_data['Distance (m)'] = '{:.2f}'.format(total_dist_m)

        if len(pos_z) > 0:
            max_alt_diff = np.amax(pos_z) - np.amin(pos_z)
            table_text_right.append(('Max Altitude Difference', "{:.0f} m".format(max_alt_diff)))
            csv_table_data['Max Altitude Distance (m)'] = '{:.0f}'.format(max_alt_diff)

        table_text_right.append(('', '')) # spacing

        # Speed
        if len(vel_x) > 0:
            #max_h_speed = np.amax(np.sqrt(np.square(vel_x) + np.square(vel_y)))
            ave_h_speed = np.mean(np.sqrt(np.square(vel_x) + np.square(vel_y)))
            speed_vector = np.sqrt(np.square(vel_x) + np.square(vel_y) + np.square(vel_z))
            max_speed = np.amax(speed_vector)
            if vtol_states is None:
                mean_speed = np.mean(speed_vector)
                table_text_right.append(('Average Speed', "{:.1f} km/h".format(mean_speed*3.6))) #*3.6 to turn m/s into km/h
                table_text_right.append(('Max Speed', "{:.1f} km/h".format(max_speed*3.6)))
                csv_table_data['Average Speed (km/h)'] = '{:.2f}'.format(mean_speed*3.6)
                csv_table_data['Max Speed (km/h)'] = '{:.2f}'.format(max_speed*3.6)
            else:
                local_pos_timestamp = local_pos.data['timestamp'][local_vel_valid_indices]
                speed_vector = speed_vector.reshape((len(speed_vector),))
                mean_speed_mc, mean_speed_fw, max_speed_mc, max_speed_fw = _get_vtol_means_per_mode(
                    vtol_states, local_pos_timestamp, speed_vector)
                if mean_speed_mc is not None:
                    table_text_right.append(('Average Speed MC', "{:.1f} km/h".format(mean_speed_mc*3.6)))
                    table_text_right.append(('Max Speed MC', "{:.1f} km/h".format(max_speed_mc*3.6)))
                    csv_table_data['Average Speed MC (km/h)'] = '{:.2f}'.format(mean_speed_mc*3.6)
                    csv_table_data['Max Speed MC (km/h)'] = '{:.2f}'.format(max_speed_mc*3.6)
                if mean_speed_fw is not None:
                    table_text_right.append(('Average Speed FW', "{:.1f} km/h".format(mean_speed_fw*3.6)))
                    table_text_right.append(('Max Speed FW', "{:.1f} km/h".format(max_speed_fw*3.6)))
                    csv_table_data['Average Speed FW (km/h)'] = '{:.2f}'.format(mean_speed_fw*3.6)
                    csv_table_data['Average Speed FW (km/h)'] = '{:.2f}'.format(max_speed_fw*3.6)
            
            # table_text_right.append(('Average Speed Horizontal', "{:.1f} km/h".format(ave_h_speed*3.6)))
            # table_text_right.append(('Max Speed Horizontal', "{:.1f} km/h".format(max_h_speed*3.6)))
            # table_text_right.append(('Max Speed Up', "{:.1f} km/h".format(np.amax(-vel_z)*3.6)))
            # table_text_right.append(('Max Speed Down', "{:.1f} km/h".format(-np.amin(-vel_z)*3.6)))
            # csv_table_data['Average Speed Horizontal (km/h)'] = ave_h_speed*3.6

            table_text_right.append(('', '')) # spacing

        # RPM 
        if any(elem.name == 'rpm' for elem in ulog.data_list):
            #rpm_data = ulog.get_dataset('rpm',0) # for other instance
            rpm_data = ulog.get_dataset('rpm')
            rpm_4 = rpm_data.data ['electrical_speed_rpm[4]'] #4th instance
            max_rpm = np.amax(rpm_4)
            average_rpm = np.mean(rpm_4)
            # table_text_right.append(('Max RPM ', "{:.2f} ".format(max_rpm)))
            # table_text_right.append(('Average RPM ', "{:.2f} ".format(average_rpm)))
            csv_table_data['Max RPM'] = '{:.2f}'.format(max_rpm)
            csv_table_data['Average RPM'] = '{:.2f}'.format(average_rpm)
        else:
            pass

        #Servo
        if any(elem.name == 'servo_status' for elem in ulog.data_list):
            servo_data = ulog.get_dataset('servo_status')
            servo_force = servo_data.data ['servo[0].servo_force']
            max_servo_force = np.amax(servo_force)
            average_servo_force = np.mean(servo_force)
            # table_text_right.append(('Max Servo Force ', "{:.2f} N".format(max_servo_force)))
            # table_text_right.append(('Average Servo Force ', "{:.2f} N".format(average_servo_force)))
            csv_table_data['Max Servo Force'] = '{:.2f}'.format(max_servo_force)
            csv_table_data['Average Servo Force'] = '{:.2f}'.format(average_servo_force)
        else:
            pass



        vehicle_attitude = ulog.get_dataset('vehicle_attitude')
        roll = vehicle_attitude.data['roll'] 
        pitch = vehicle_attitude.data['pitch']
        if len(roll) > 0:
            # tilt = angle between [0,0,1] and [0,0,1] rotated by roll and pitch
            tilt_angle = np.arccos(np.multiply(np.cos(pitch), np.cos(roll)))*180/np.pi
            # table_text_right.append(('Average Tilt Angle', "{:.1f} deg".format(np.mean(tilt_angle))))
            # table_text_right.append(('Max Tilt Angle', "{:.1f} deg".format(np.amax(tilt_angle))))
            csv_table_data['Average Tilt Angle (deg)'] = '{:.2f}'.format(np.mean(tilt_angle))
            csv_table_data['Max Tilt Angle (deg)'] = '{:.2f}'.format(np.amax(tilt_angle))

        # Bug if uncomment, the plot command under this will not working
        # rollspeed = vehicle_attitude.data['rollspeed']
        # pitchspeed = vehicle_attitude.data['pitchspeed']
        # yawspeed = vehicle_attitude.data['yawspeed']
        # if len(rollspeed) > 0:
        #     max_rot_speed = np.amax(np.sqrt(np.square(rollspeed) +
        #                                     np.square(pitchspeed) +
        #                                     np.square(yawspeed)))
        #     # table_text_right.append(('Max Rotation Speed', "{:.1f} deg/s".format(
        #     #     max_rot_speed*180/np.pi)))
        #     csv_table_data['Max Rotation Speed (deg/s)'] = max_rot_speed*180/np.pi

        #Battery Current and voltage
        count_battery = sum(1 for n in ulog.data_list if n.name == 'battery_status')
        for i in range (count_battery): #len battery_status instance
            battery_status = ulog.get_dataset('battery_status',i)
            battery_current = battery_status.data['current_a']
            battery_voltage = battery_status.data['voltage_v']
            max_current = np.amax(battery_current)
            if len(battery_current) > 0 and np.mean(battery_current) > 1:
                if vtol_states is None:
                    mean_current = np.mean(battery_current)
                    table_text_right.append(('Avg/Max Current', "{:.1f}/ {:.1f} A ".format(mean_current,max_current)))
                    csv_table_data['Average Current (A)'] = mean_current
                    csv_table_data['Max Current (A)'] = max_current
                else:
                    mean_current_mc, mean_current_fw, max_current_mc, max_current_fw = _get_vtol_means_per_mode(
                        vtol_states, battery_status.data['timestamp'], battery_current)
                    if mean_current_mc is not None:
                        table_text_right.append(
                            ('Avg/Max Current MC', "{:.1f}/ {:.1f} A".format(mean_current_mc,max_current_mc)))
                        csv_table_data['Average Current MC (A)'] = '{:.2f}'.format(mean_current_mc)
                        csv_table_data['Max Current MC (A)'] = '{:.2f}'.format(max_current_mc)
                    if mean_current_fw is not None:
                        table_text_right.append(
                            ('Avg/Max Current FW', "{:.1f}/ {:.1f} A".format(mean_current_fw,max_current_fw)))
                        csv_table_data['Average Current FW (A)'] = '{:.2f}'.format(mean_current_fw)
                        csv_table_data['Max Current FW (A)'] = '{:.2f}'.format(max_current_fw)

                begin_voltage = battery_voltage[0]
                end_voltage = battery_voltage[-1]
                table_text_right.append(
                    ('Begin/End Voltage', "{:.1f}/ {:.1f} V".format(begin_voltage,end_voltage)))
                csv_table_data['Begin Voltage (V)'] = '{:.2f}'.format(begin_voltage)
                csv_table_data['End Voltage (V)'] = '{:.2f}'.format(end_voltage)


    except:
        pass # ignore (e.g. if topic not found)


    # generate the tables
    def generate_html_table(rows_list, tooltip=None, max_width=None):
        """
        return the html table (str) from a row list of tuples
        """
        if tooltip is None:
            tooltip = ''
        else:
            tooltip = 'data-toggle="tooltip" data-placement="left" '+ \
                'data-delay=\'{"show": 1000, "hide": 100}\' title="'+tooltip+'" '
        table = '<table '+tooltip
        if max_width is not None:
            table += ' style="max-width: '+max_width+';"'
        table += '>'
        padding_text = ''
        for label, value in rows_list:
            if label == '': # empty label means: add some row spacing
                padding_text = ' style="padding-top: 0.5em;" '
            else:
                table += ('<tr><td '+padding_text+'class="left">'+label+
                          ':</td><td'+padding_text+'>'+value+'</td></tr>')
                padding_text = ''
        return table + '</table>'

    left_table = generate_html_table(table_text_left, max_width='65%') #65
    right_table = generate_html_table(
        table_text_right,
        'Note: most of these values are based on estimations from the vehicle,'
        ' and thus require an accurate estimator')
    html_tables = ('<p><div style="display: flex; justify-content: space-between;">'+
                   left_table+right_table+'</div></p>')
    # Save 
    saved_log_path = os.path.expanduser('~/Flight_review_git/flight_review/app/saved_log/')
    if any(elem.name == 'vehicle_gps_position' for elem in ulog.data_list):
        save_name = saved_log_path + logging_start_formatted
    else:
        save_name = saved_log_path + 'no_date_display'

    save_csv_file(save_name)

    save_pdf_file(save_name)

    return html_tables

def save_csv_file(saved_name):
    #save csv file
    with open(saved_name +'.csv', 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        
        csv_writer.writerow(['Title', 'Value']) # write the headers
        
        for key, value in csv_table_data.items(): # write the data from dict
            csv_writer.writerow([key, value])

    print('CSV data has been saved')
    return None

def save_pdf_file(saved_name):
    #save pdf file
    pdf_file = canvas.Canvas(saved_name + '.pdf', pagesize=A4)
    font_size = 8
    pdf_file.setFont('Helvetica', font_size)    
    
    y_coordinate = A4[1]-50 #set start position 841.89-50 points (1 inch = 72 pts)

    for key, value in csv_table_data.items(): #loop for adding text from dict
        text = f"{key}: {value}"
        pdf_file.drawString(50, y_coordinate, text)
        y_coordinate -= 15  # Move to the next line

    pdf_file.save()
    print('PDF data has been saved')
    return None

def get_error_labels_html():
    """
    Get the html (as string) for user-selectable error labels
    """
    error_label_select = \
        '<select id="error-label" class="chosen-select" multiple="True" '\
        'style="display: none; " tabindex="-1" ' \
        'data-placeholder="Add a detected error..." " >'
    for err_id, err_label in error_labels_table.items():
        error_label_select += '<option data-id="{:d}">{:s}</option>'.format(err_id, err_label)
    error_label_select = '<p>' + error_label_select + '</select></p>'

    return error_label_select

def get_corrupt_log_html(ulog):
    """
    Get the html (as string) for corrupt logs,
    if the log is corrupt, otherwise returns None
    """
    if ulog.file_corruption:
        corrupt_log_html = """
<div class="card text-white bg-danger mb-3">
  <div class="card-header">Warning</div>
  <div class="card-body">
    <h4 class="card-title">Corrupt Log File</h4>
    <p class="card-text">
        This log contains corrupt data. Some of the shown data might be wrong
        and some data might be missing.
        <br />
        A possible cause is a corrupt file system and exchanging or reformatting
        the SD card fixes the problem.
        </p>
  </div>
</div>
"""
        return corrupt_log_html
    return None

def get_hardfault_html(ulog):
    """
    Get the html (as string) for hardfault information,
    if the log contains any, otherwise returns None
    """
    if 'hardfault_plain' in ulog.msg_info_multiple_dict:

        hardfault_html = """
<div class="card text-white bg-danger mb-3">
  <div class="card-header">Warning</div>
  <div class="card-body">
    <h4 class="card-title">Software Crash</h4>
    <p class="card-text">
        This log contains hardfault data from a software crash
        (see <a style="color:#fff; text-decoration: underline;"
        href="https://docs.px4.io/master/en/debug/gdb_debugging.html#hard-fault-debugging">
        here</a> how to debug).
        <br/>
        The hardfault data is shown below.
        </p>
  </div>
</div>
"""

        counter = 1
        for hardfault in ulog.msg_info_multiple_dict['hardfault_plain']:
            hardfault_text = escape(''.join(hardfault)).replace('\n', '<br/>')
            hardfault_html += ('<p>Hardfault #'+str(counter)+':<br/><pre>'+
                               hardfault_text+'</pre></p>')
            counter += 1
        return hardfault_html
    return None

def get_changed_parameters(ulog, plot_width):
    """
    get a bokeh column object with a table of the changed parameters
    :param initial_parameters: ulog.initial_parameters
    """
    param_names = []
    param_values = []
    param_defaults = []
    param_mins = []
    param_maxs = []
    param_descriptions = []
    param_colors = []
    default_params = get_default_parameters()
    initial_parameters = ulog.initial_parameters
    system_defaults = None
    airframe_defaults = None
    if ulog.has_default_parameters:
        system_defaults = ulog.get_default_parameters(0)
        airframe_defaults = ulog.get_default_parameters(1)

    for param_name in sorted(initial_parameters):
        param_value = initial_parameters[param_name]

        if param_name.startswith('RC') or param_name.startswith('CAL_'):
            continue

        system_default = None
        airframe_default = None
        is_airframe_default = True
        if system_defaults is not None:
            system_default = system_defaults.get(param_name, param_value)
        if airframe_defaults is not None:
            airframe_default = airframe_defaults.get(param_name, param_value)
            is_airframe_default = abs(float(airframe_default) - float(param_value)) < 0.00001

        try:
            if param_name in default_params:
                default_param = default_params[param_name]
                if system_default is None:
                    system_default = default_param['default']
                    airframe_default = default_param['default']
                if default_param['type'] == 'FLOAT':
                    is_default = abs(float(system_default) - float(param_value)) < 0.00001
                    if 'decimal' in default_param:
                        param_value = round(param_value, int(default_param['decimal']))
                        airframe_default = round(float(airframe_default), int(default_param['decimal'])) #pylint: disable=line-too-long
                else:
                    is_default = int(system_default) == int(param_value)
                if not is_default:
                    param_names.append(param_name)
                    param_values.append(param_value)
                    param_defaults.append(airframe_default)
                    param_mins.append(default_param.get('min', ''))
                    param_maxs.append(default_param.get('max', ''))
                    param_descriptions.append(default_param.get('short_desc', ''))
                    param_colors.append('black' if is_airframe_default else plot_color_red)
            else:
                # not found: add it as if it were changed
                param_names.append(param_name)
                param_values.append(param_value)
                param_defaults.append(airframe_default if airframe_default else '')
                param_mins.append('')
                param_maxs.append('')
                param_descriptions.append('(unknown)')
                param_colors.append('black' if is_airframe_default else plot_color_red)
        except Exception as error:
            print(type(error), error)
    param_data = {
        'names': param_names,
        'values': param_values,
        'defaults': param_defaults,
        'mins': param_mins,
        'maxs': param_maxs,
        'descriptions': param_descriptions,
        'colors': param_colors
        }
    source = ColumnDataSource(param_data)
    formatter = HTMLTemplateFormatter(template='<font color="<%= colors %>"><%= value %></font>')
    columns = [
        TableColumn(field="names", title="Name",
                    width=int(plot_width*0.2), sortable=False),
        TableColumn(field="values", title="Value",
                    width=int(plot_width*0.15), sortable=False, formatter=formatter),
        TableColumn(field="defaults",
                    title="Frame Default" if airframe_defaults else "Default",
                    width=int(plot_width*0.1), sortable=False),
        TableColumn(field="mins", title="Min",
                    width=int(plot_width*0.075), sortable=False),
        TableColumn(field="maxs", title="Max",
                    width=int(plot_width*0.075), sortable=False),
        TableColumn(field="descriptions", title="Description",
                    width=int(plot_width*0.40), sortable=False),
        ]
    data_table = DataTable(source=source, columns=columns, width=plot_width,
                           height=300, sortable=False, selectable=False,
                           autosize_mode='none')
    div = Div(text="""<b>Non-default Parameters</b> (except RC and sensor calibration)""",
              width=int(plot_width/2))
    return column(div, data_table, width=plot_width)


def get_logged_messages(ulog, plot_width):
    """
    get a bokeh column object with a table of the logged text messages and events
    :param ulog: ULog object
    """
    messages = get_logged_events(ulog)

    def time_str(t):
        m1, s1 = divmod(int(t/1e6), 60)
        h1, m1 = divmod(m1, 60)
        return "{:d}:{:02d}:{:02d}".format(h1, m1, s1)

    logged_messages = ulog.logged_messages
    for m in logged_messages:
        # backwards compatibility: a string message with appended tab is output
        # in addition to an event with the same message so we can ignore those
        if m.message[-1] == '\t':
            continue
        messages.append((m.timestamp, m.log_level_str(), m.message))

    messages = sorted(messages, key=lambda m: m[0])

    log_times, log_levels, log_messages = zip(*messages) if len(messages) > 0 else ([],[],[])
    log_times_str = [time_str(t) for t in log_times]
    log_data = {
        'times': log_times_str,
        'levels': log_levels,
        'messages': log_messages
        }
    source = ColumnDataSource(log_data)
    columns = [
        TableColumn(field="times", title="Time",
                    width=int(plot_width*0.15), sortable=False),
        TableColumn(field="levels", title="Level",
                    width=int(plot_width*0.1), sortable=False),
        TableColumn(field="messages", title="Message",
                    width=int(plot_width*0.75), sortable=False),
        ]
    data_table = DataTable(source=source, columns=columns, width=plot_width,
                           height=300, sortable=False, selectable=False,
                           autosize_mode='none')
    div = Div(text="""<b>Logged Messages</b>""", width=int(plot_width/2))
    return column(div, data_table, width=plot_width)
