# --- Create Subzones with 2019 Variables Script ---

import arcpy
import os
import pandas as pd
import time
import numpy as np

print(f"ArcPy version: {arcpy.GetInstallInfo()['Version']}")
print("Starting script: create_subzone_variables.py...")

# --- Configuration ---
script_dir = os.path.dirname(os.path.abspath(__file__))
print(f"Script directory (base path): {script_dir}")
input_dir_prep = os.path.join(script_dir, "satscan_inputs_2019")
input_dir_dl = os.path.join(script_dir, "downloaded_data_2019")

boundary_shp = os.path.join(input_dir_prep, "subzone_boundaries_svy21_standardized.shp")
dengue_points_shp = os.path.join(input_dir_dl, f"dengue_points_2019-05-01_to_2019-07-31.shp")
temp_csv = os.path.join(input_dir_dl, "temperature_2019-03-01_to_2019-05-31_with_coords.csv")
rain_csv = os.path.join(input_dir_dl, "rainfall_2019-03-01_to_2019-05-31_with_coords.csv")
pop_csv = os.path.join(input_dir_dl, "population_subzone_processed.csv")
ndvi_raster_file = os.path.join(input_dir_dl, "Singapore_NDVI_2019_May_Jul.tif") 

# --- Output Configuration ---
output_dir = os.path.join(script_dir, "analysis_inputs_2019")
output_shp = os.path.join(output_dir, "subzones_with_2019_variables.shp") # Save to SHP
output_gdb = os.path.join(output_dir, "temp_processing.gdb")

# --- Field Names ---
subzone_id_field = "Location_I"
case_count_field = "CaseCnt19"
avg_temp_field = "AvgTmpLg19"
avg_rain_field = "AvgRnLg19"
avg_ndvi_field = "AvgNDVI19"
pop_density_field = "PopDen20"
area_field = "Area_KM2"

ahp_variable_fields = [
    case_count_field, 
    avg_temp_field, 
    avg_rain_field, 
    avg_ndvi_field, 
    pop_density_field
]

name_mapping = {
    "MANDAI ESTATE": "MANDAI EAST",
    "YIO CHU KANG": "YIO CHU KANG EAST",
    "TIONG BAHRU STATION": "TIONG BAHRU",
}
name_mapping = {k.upper().strip(): v.upper().strip() for k, v in name_mapping.items()}

kriging_cell_size = 50
kriging_search_radius = "VARIABLE 12"

# --- Setup ---
arcpy.env.overwriteOutput = True
os.makedirs(output_dir, exist_ok=True)
if not arcpy.Exists(output_gdb):
    arcpy.management.CreateFileGDB(output_dir, "temp_processing.gdb")
arcpy.env.workspace = output_gdb
print(f"Temporary workspace set to: {output_gdb}")
if arcpy.CheckExtension("Spatial") == "Available":
    arcpy.CheckOutExtension("Spatial")
    print("Spatial Analyst extension checked out.")
else:
    print("ERROR: Spatial Analyst extension is not available.")
    exit()

# --- 1. Prepare Base Subzone Layer ---
print(f"Copying base subzone layer from: {boundary_shp}")
if not arcpy.Exists(boundary_shp):
    print(f"FATAL ERROR: Input file not found at {boundary_shp}")
    exit()
    
subzone_layer = "subzones_base"
arcpy.conversion.FeatureClassToFeatureClass(boundary_shp, output_gdb, subzone_layer)
print(f"Base layer '{subzone_layer}' created with ID field '{subzone_id_field}'.")
target_sr = arcpy.Describe(subzone_layer).spatialReference

# --- 2. Calculate Case Counts ---
print("Calculating dengue case counts per subzone...")
count_join_layer = "subzones_with_counts"
try:
    if not arcpy.Exists(dengue_points_shp):
        raise FileNotFoundError(f"Dengue points file not found: {dengue_points_shp}")
    
    arcpy.analysis.SpatialJoin(
        target_features=subzone_layer,
        join_features=dengue_points_shp,
        out_feature_class=count_join_layer,
        join_operation="JOIN_ONE_TO_ONE",
        join_type="KEEP_ALL", 
        match_option="INTERSECT"
    )
    join_count_field_actual = "Join_Count"
    field_names = [f.name for f in arcpy.ListFields(count_join_layer)]
    if join_count_field_actual in field_names:
        arcpy.management.AlterField(count_join_layer, join_count_field_actual, case_count_field, case_count_field)
        arcpy.management.CalculateField(count_join_layer, case_count_field, f"!{case_count_field}! if !{case_count_field}! is not None else 0", "PYTHON3")
        print(f"Case count field '{case_count_field}' added.")
    else:
        print(f"Warning: 'Join_Count' field not found. Adding empty '{case_count_field}'.")
        arcpy.management.AddField(count_join_layer, case_count_field, "LONG", field_is_nullable=True)
        arcpy.management.CalculateField(count_join_layer, case_count_field, "0", "PYTHON3")
    current_subzone_layer = count_join_layer
except Exception as e:
    print(f"ERROR during case count spatial join: {e}")
    current_subzone_layer = subzone_layer
    if not arcpy.ListFields(current_subzone_layer, case_count_field):
        arcpy.management.AddField(current_subzone_layer, case_count_field, "LONG", field_is_nullable=True)
    arcpy.management.CalculateField(current_subzone_layer, case_count_field, "0", "PYTHON3")
    print(f"Added empty field '{case_count_field}' due to spatial join error.")


# --- 3. Interpolate Weather Data ---
print("Processing and interpolating weather data...")
weather_coords_sys = arcpy.SpatialReference(4326) 

def interpolate_weather(csv_path_with_coords, value_field_in_csv, output_raster_name, aggregation_method='mean_of_all_readings'):
    """
    Interpolates weather data from a CSV.
    - 'mean_of_all_readings': (Default) Averages all readings. Use for Temperature.
    - 'mean_of_daily_sums': Sums readings by day, then averages those daily sums. Use for Rainfall.
    """
    print(f"  Interpolating {output_raster_name} from {os.path.basename(csv_path_with_coords)}...")
    try:
        if not os.path.exists(csv_path_with_coords):
            raise FileNotFoundError(f"Weather CSV not found: {csv_path_with_coords}")
        df = pd.read_csv(csv_path_with_coords)
        
        # Check for required columns based on method
        required_cols = ['latitude', 'longitude', value_field_in_csv, 'station_id']
        if aggregation_method == 'mean_of_daily_sums':
            required_cols.append('date_retrieved')
        if not all(col in df.columns for col in required_cols):
             raise ValueError(f"CSV {csv_path_with_coords} must contain columns: {required_cols}")

        df[value_field_in_csv] = pd.to_numeric(df[value_field_in_csv], errors='coerce')
        df.dropna(subset=[value_field_in_csv, 'latitude', 'longitude'], inplace=True)
        
        # --- Aggregation Logic ---
        if aggregation_method == 'mean_of_daily_sums':
            # 1. Calculate the SUM of readings for each station, for each day
            print("    Aggregating by day (sum)...")
            daily_sum_df = df.groupby(['station_id', 'latitude', 'longitude', 'date_retrieved'])[value_field_in_csv].sum().reset_index()
            # 2. Calculate the MEAN of those daily sums for each station
            print("    Averaging daily sums (mean)...")
            avg_df = daily_sum_df.groupby(['station_id', 'latitude', 'longitude'])[value_field_in_csv].mean().reset_index()
            print(f"    Aggregated data to {len(avg_df)} unique stations using MEAN of DAILY SUMS.")
        
        else: # default: 'mean_of_all_readings'
            # This is for temperature. Average all readings.
            print("    Aggregating by station (mean)...")
            avg_df = df.groupby(['station_id', 'latitude', 'longitude'])[value_field_in_csv].mean().reset_index()
            print(f"    Aggregated data to {len(avg_df)} unique stations using MEAN.")
        # --- End Aggregation Logic ---

        if avg_df.empty: raise ValueError("No valid station data after aggregation.")
        
        points_layer = f"{output_raster_name}_points"
        temp_csv_for_xy = os.path.join(arcpy.env.scratchFolder, f"{output_raster_name}_avg.csv")
        avg_df.to_csv(temp_csv_for_xy, index=False)
        print(f"    Creating point layer '{points_layer}'...")
        arcpy.management.XYTableToPoint(
            in_table=temp_csv_for_xy,
            out_feature_class=points_layer,
            x_field="longitude",
            y_field="latitude",
            coordinate_system=weather_coords_sys
        )
        points_layer_svy21 = f"{points_layer}_svy21"
        print(f"    Projecting points to SVY21...")
        arcpy.management.Project(points_layer, points_layer_svy21, target_sr)
        print(f"    Running Kriging for {output_raster_name}...")
        kriging_model = arcpy.sa.KrigingModelOrdinary("SPHERICAL")
        kriging_output = arcpy.sa.Kriging(
            in_point_features=points_layer_svy21,
            z_field=value_field_in_csv,
            kriging_model=kriging_model,
            cell_size=kriging_cell_size,
            search_radius=kriging_search_radius
        )
        arcpy.env.mask = current_subzone_layer
        kriging_output.save(output_raster_name)
        print(f"    Interpolated raster saved: {output_raster_name}")
        arcpy.management.Delete(points_layer)
        arcpy.management.Delete(points_layer_svy21)
        return output_raster_name
    except Exception as e:
        print(f"ERROR interpolating {output_raster_name}: {e}")
        return None
    finally:
        arcpy.env.mask = None

# Call for Temperature (default method: 'mean_of_all_readings')
temp_raster = interpolate_weather(temp_csv, 'value', 'temp_lagged_2019', 'mean_of_all_readings') 

# Call for Rainfall (FIXED method: 'mean_of_daily_sums')
rain_raster = interpolate_weather(rain_csv, 'value', 'rain_lagged_2019', 'mean_of_daily_sums')


# --- 4. Prepare NDVI Raster ---
print("Preparing pre-processed NDVI raster...")
ndvi_raster_gdb = "ndvi_2019_projected"
try:
    if not os.path.exists(ndvi_raster_file) and not arcpy.Exists(ndvi_raster_file):
        raise FileNotFoundError(f"NDVI file not found at: {ndvi_raster_file}")
    
    print(f"  Projecting NDVI raster to {target_sr.name}...")
    arcpy.management.ProjectRaster(
        in_raster=ndvi_raster_file,
        out_raster=ndvi_raster_gdb,
        out_coor_system=target_sr,
        resampling_type="BILINEAR", 
        cell_size=kriging_cell_size 
    )
    print(f"  NDVI raster projected and saved as: {ndvi_raster_gdb}")
except Exception as e:
    print(f"ERROR preparing NDVI raster: {e}")
    ndvi_raster_gdb = None

# --- 5. Calculate Zonal Statistics ---
print("Calculating zonal statistics for weather and NDVI...")
rasters_to_analyze = [temp_raster, rain_raster, ndvi_raster_gdb] 
output_field_names = [avg_temp_field, avg_rain_field, avg_ndvi_field]
zone_field = subzone_id_field # 'Location_I'

for i in range(len(rasters_to_analyze)):
    raster = rasters_to_analyze[i]
    out_field = output_field_names[i]
    if raster and arcpy.Exists(raster):
        print(f"  Calculating zonal stats for {raster}...")
        temp_table = f"zonal_stats_{raster}"
        try:
            arcpy.env.extent = arcpy.Describe(raster).extent
            arcpy.sa.ZonalStatisticsAsTable(
                in_zone_data=current_subzone_layer,
                zone_field=zone_field,
                in_value_raster=raster,
                out_table=temp_table,
                statistics_type="MEAN",
                ignore_nodata="DATA"
            )
            arcpy.env.extent = None
            
            arcpy.management.JoinField(
                in_data=current_subzone_layer,
                in_field=zone_field,
                join_table=temp_table,
                join_field=zone_field,
                fields=["MEAN"]
            )
            mean_field_actual = "MEAN"
            joined_fields = [f.name for f in arcpy.ListFields(current_subzone_layer)]
            if mean_field_actual in joined_fields:
                arcpy.management.AlterField(current_subzone_layer, mean_field_actual, out_field, out_field)
                arcpy.management.CalculateField(current_subzone_layer, out_field, f"!{out_field}! if !{out_field}! is not None else 0", "PYTHON3")
                print(f"    Zonal stats joined. Field '{out_field}' added.")
            else:
                 print(f"    Warning: 'MEAN' field not found after join for {raster}. Adding empty '{out_field}'.")
                 if not arcpy.ListFields(current_subzone_layer, out_field):
                     arcpy.management.AddField(current_subzone_layer, out_field, "DOUBLE")
                 arcpy.management.CalculateField(current_subzone_layer, out_field, "0", "PYTHON3")

            arcpy.management.Delete(temp_table)
        except Exception as e:
            print(f"ERROR calculating or joining zonal stats for {raster}: {e}")
            if not arcpy.ListFields(current_subzone_layer, out_field):
                 arcpy.management.AddField(current_subzone_layer, out_field, "DOUBLE")
            arcpy.management.CalculateField(current_subzone_layer, out_field, "0", "PYTHON3")
            print(f"    Set field '{out_field}' to 0 due to error.")
    else:
        print(f"Skipping zonal stats for missing/failed raster: {raster}")
        if not arcpy.ListFields(current_subzone_layer, out_field):
             arcpy.management.AddField(current_subzone_layer, out_field, "DOUBLE")
        arcpy.management.CalculateField(current_subzone_layer, out_field, "0", "PYTHON3")
        print(f"    Set field '{out_field}' to 0.")

# --- 6. Calculate Population Density ---
print("Calculating population density...")
try:
    pop_df = pd.read_csv(pop_csv)
    pop_df['Location_ID_Std'] = pop_df['Subzone_Name'].astype(str).str.strip().str.upper()
    pop_df['Location_ID_Mapped'] = pop_df['Location_ID_Std'].map(name_mapping).fillna(pop_df['Location_ID_Std'])
    pop_df.rename(columns={'Location_ID_Mapped': subzone_id_field}, inplace=True) # 'Location_I'
    pop_join_csv = os.path.join(arcpy.env.scratchFolder, "pop_for_join.csv")
    pop_df_to_join = pop_df[[subzone_id_field, "Population_2020"]].drop_duplicates()
    pop_df_to_join.to_csv(pop_join_csv, index=False)

    arcpy.management.JoinField(
        in_data=current_subzone_layer,
        in_field=subzone_id_field, # 'Location_I'
        join_table=pop_join_csv,
        join_field=subzone_id_field, # 'Location_I'
        fields=["Population_2020"]
    )
    pop_field = "Population_2020"
    joined_fields = [f.name for f in arcpy.ListFields(current_subzone_layer)]
    if pop_field in joined_fields:
        arcpy.management.CalculateField(current_subzone_layer, pop_field, f"!{pop_field}! if !{pop_field}! is not None else 0", "PYTHON3")

        arcpy.management.AddField(current_subzone_layer, area_field, "DOUBLE")
        arcpy.management.CalculateGeometryAttributes(
            in_features=current_subzone_layer,
            geometry_property=[[area_field, "AREA_GEODESIC"]],
            area_unit="SQUARE_KILOMETERS"
        )
        arcpy.management.AddField(current_subzone_layer, pop_density_field, "DOUBLE")
        expression = f"!{pop_field}! / !{area_field}! if !{area_field}! is not None and !{area_field}! > 0 else 0"
        arcpy.management.CalculateField(current_subzone_layer, pop_density_field, expression, "PYTHON3")
        print(f"Population density field '{pop_density_field}' added.")
    else:
        print(f"Warning: Population field '{pop_field}' not found after join. Adding empty density field.")
        if not arcpy.ListFields(current_subzone_layer, area_field): arcpy.management.AddField(current_subzone_layer, area_field, "DOUBLE")
        if not arcpy.ListFields(current_subzone_layer, pop_density_field): arcpy.management.AddField(current_subzone_layer, pop_density_field, "DOUBLE")
        arcpy.management.CalculateField(current_subzone_layer, pop_density_field, "0", "PYTHON3")
except Exception as e:
    print(f"ERROR calculating population density: {e}")
    if not arcpy.ListFields(current_subzone_layer, area_field): arcpy.management.AddField(current_subzone_layer, area_field, "DOUBLE")
    if not arcpy.ListFields(current_subzone_layer, pop_density_field): arcpy.management.AddField(current_subzone_layer, pop_density_field, "DOUBLE")
    arcpy.management.CalculateField(current_subzone_layer, pop_density_field, "0", "PYTHON3")
    print(f"    Set field '{pop_density_field}' to 0 due to error.")

# --- 7. Final Output ---
print(f"Saving final output layer to: {output_shp}...")
try:
    final_fields_present = [f for f in ahp_variable_fields if arcpy.ListFields(current_subzone_layer, f)]
    print(f"Final fields present for export: {final_fields_present}")
    
    field_mappings = arcpy.FieldMappings()
    field_mappings.addTable(current_subzone_layer)
    fields_to_keep_names = [subzone_id_field] + final_fields_present
    desc = arcpy.Describe(current_subzone_layer)
    fields_to_keep_names.extend([desc.shapeFieldName, desc.OIDFieldName])
    fields_to_keep = set(fields_to_keep_names)
    maps_to_remove = []
    for i in range(field_mappings.fieldCount):
        field_map = field_mappings.getFieldMap(i)
        if field_map.outputField.name not in fields_to_keep:
            maps_to_remove.append(i)
    for i in sorted(maps_to_remove, reverse=True):
        field_mappings.removeFieldMap(i)

    arcpy.conversion.FeatureClassToFeatureClass(
        in_features=current_subzone_layer,
        out_path=os.path.dirname(output_shp),
        out_name=os.path.basename(output_shp),
        field_mapping=field_mappings
    )
    print(f"Successfully saved final Shapefile: {output_shp}")
except Exception as e:
    print(f"ERROR saving final Shapefile: {e}")

# --- Cleanup ---
arcpy.CheckInExtension("Spatial")
print("Spatial Analyst extension checked in.")