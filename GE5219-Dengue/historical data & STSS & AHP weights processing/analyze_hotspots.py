# --- Analyze Hotspot Variables Script ---
#
# This script reads the final subzone variables Shapefile AND
# the SaTScan output .gis.shp file to compare average variable
# values for hotspot vs. non-hotspot subzones.

import os
import re
import pandas as pd
import geopandas as gpd
import numpy as np

# --- 1. Configuration ---
script_dir = os.path.dirname(os.path.abspath(__file__))
print(f"Script directory (base path): {script_dir}")

# Path to the Shapefile containing all subzones and their 5 variables
SUBZONE_VARIABLES_FILE = os.path.join(script_dir, "analysis_inputs_2019", "subzones_with_2019_variables.shp")

# Path to the SaTScan GIS output shapefile
SATSCAN_GIS_SHP = os.path.join(script_dir, "satscan_outputs_2019", "2019_Hotspot_Analysis_Results.gis.shp")


# --- Field Names ---
SUBZONE_ID_FIELD = "Location_I" 

AHP_VARIABLE_FIELDS = [
    'CaseCnt19',
    'AvgTmpLg19',
    'AvgRnLg19',
    'AvgNDVI19',
    'PopDen20'
]

# --- End of Configuration ---

def main():
    print("--- Starting Hotspot Variable Analysis for AHP ---")

    # --- Step 1: Get Hotspot Subzone IDs from SaTScan .gis.shp ---
    print(f"Reading hotspot location IDs from: {SATSCAN_GIS_SHP}")
    try:
        hotspot_gis_gdf = gpd.read_file(SATSCAN_GIS_SHP)
        # The SaTScan .gis.shp file has a 'LOC_ID' field with full names
        if 'LOC_ID' not in hotspot_gis_gdf.columns:
            print(f"FATAL ERROR: 'LOC_ID' column not found in {SATSCAN_GIS_SHP}.")
            return
            
        # Get a clean set of standardized, full-text names
        full_hotspot_names = set(hotspot_gis_gdf['LOC_ID'].astype(str).str.strip().str.upper())
        print(f"Found {len(full_hotspot_names)} unique full-text hotspot subzone names.")

    except Exception as e:
        print(f"FATAL ERROR: Could not read SaTScan GIS file at {SATSCAN_GIS_SHP}.")
        print(f"Error: {e}")
        return
    
    # --- Step 2: Load Subzone Variables Data ---
    print(f"\nLoading subzone variables from: {SUBZONE_VARIABLES_FILE}")
    try:
        gdf = gpd.read_file(SUBZONE_VARIABLES_FILE)
    except Exception as e:
        print(f"FATAL ERROR: Could not read variables Shapefile at {SUBZONE_VARIABLES_FILE}.")
        print(f"Error: {e}")
        return
        
    print(f"Loaded {len(gdf)} total subzones from variables Shapefile.")

    # --- Step 3: Verify All Fields Exist ---
    required_fields = [SUBZONE_ID_FIELD] + AHP_VARIABLE_FIELDS
    missing_fields = [f for f in required_fields if f not in gdf.columns]
    
    if missing_fields:
        print(f"FATAL ERROR: The variables Shapefile is missing required fields: {missing_fields}")
        return
        
    # --- Step 4: Tag Hotspots vs. Non-Hotspots ---
    
    # Standardize the ID field from the variables file
    gdf[SUBZONE_ID_FIELD] = gdf[SUBZONE_ID_FIELD].astype(str).str.strip().str.upper()
    
    # Convert AHP fields to numeric
    for col in AHP_VARIABLE_FIELDS:
        gdf[col] = pd.to_numeric(gdf[col], errors='coerce').fillna(0)

    # Compare the full-name list directly to the full-name column.
    gdf['is_hotspot'] = gdf[SUBZONE_ID_FIELD].isin(full_hotspot_names)
    
    hotspot_gdf = gdf[gdf['is_hotspot'] == True]
    non_hotspot_gdf = gdf[gdf['is_hotspot'] == False]
    
    num_hotspots = len(hotspot_gdf)
    num_non_hotspots = len(non_hotspot_gdf)
    
    print(f"\nSuccessfully tagged {num_hotspots} subzones as HOTSPOTS.")
    print(f"Successfully tagged {num_non_hotspots} subzones as NON-HOTSPOTS.")
    
    if num_hotspots == 0:
        print("FATAL ERROR: No subzones were matched as hotspots. Check ID field names.")
        return
    elif num_hotspots != len(full_hotspot_names):
         print(f"Warning: Matched {num_hotspots} hotspots, but expected {len(full_hotspot_names)}. Check for name mismatches.")


    # --- Step 5: Calculate Averages ---
    hotspot_averages = hotspot_gdf[AHP_VARIABLE_FIELDS].mean()
    non_hotspot_averages = non_hotspot_gdf[AHP_VARIABLE_FIELDS].mean()
    
    # --- Step 6: Create Comparison DataFrames ---
    results_df = pd.DataFrame({
        'Hotspot_Avg': hotspot_averages,
        'Non_HotSpt_Avg': non_hotspot_averages
    })
    
    ratio = np.divide(
        hotspot_averages, 
        non_hotspot_averages, 
        out=np.full_like(hotspot_averages, np.nan),
        where=non_hotspot_averages!=0
    )
    results_df['Ratio (Hotspot/Non)'] = ratio
    
    # --- Step 7: Print Formatted Output ---
    print("\n\n" + "="*50)
    print("     AHP Variable Averages (2019 Data)")
    print("="*50)
    print(results_df.to_string(
        columns=['Hotspot_Avg', 'Non_HotSpt_Avg'],
        float_format="%.4f"
    ))
    
    print("\n\n" + "="*50)
    print("     AHP Variable Ratios (Hotspot / Non-Hotspot)")
    print("="*50)
    print(results_df[['Ratio (Hotspot/Non)']].to_string(
        float_format="%.4f"
    ))
    print("\n--- Interpretation ---")
    print("Ratios > 1.0 indicate the variable is higher, on average, in hotspots.")
    print("Ratios < 1.0 indicate the variable is lower, on average, in hotspots.")
    print("="*50)


if __name__ == "__main__":
    main()