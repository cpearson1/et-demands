#!/usr/bin/env python

from collections import defaultdict
import datetime
import logging
import math
import os
import pprint
import re
import sys
import time

from dbfread import DBF
import numpy as np
import pandas as pd

import crop_et_data
import util

class ETCellData():
    """Functions for loading ET Cell data from the static text files"""
    def __init__(self):
        """ """
        self.et_cells_dict = dict()
        self.crop_num_list = []

    def set_cell_properties(self, fn, delimiter='\t'):
        """Extract the ET cell property data from the text file
    
        This function will build the ETCell objects and must be run first.
    
        Args:
            fn (str): file path of the ET cell properties text file
            delimiter (str): file delimiter (i.e. space, comma, tab, etc.)
        """
        logging.info('\nSetting static cell properties')
        a = np.loadtxt(fn, delimiter=delimiter, dtype='str')
        ## Klamath file has one header, other has two lines
        if a[0,0] == 'ET Cell ID':
            a = a[1:]
        else:
            a = a[2:]
        for i, row in enumerate(a):
            cell = ETCell()
            cell.init_properties_from_row(row)
            cell.source_file_properties = fn
            self.et_cells_dict[cell.cell_id] = cell
    
    def set_cell_crops(self, fn, delimiter='\t'):
        """Extract the ET cell crop data from the text file
    
        Args:
            fn (str): file path  of the ET cell crops text file
            delimiter (str): file delimiter (i.e. space, comma, tab, etc.)
        """
        logging.info('Setting static cell crops')
        a = np.loadtxt(fn, delimiter=delimiter, dtype='str')
        crop_numbers = a[1,4:].astype(int)
        crop_names = a[2,4:]
        a = a[3:]
        for i, row in enumerate(a):
            cell_id = row[0]
            if cell_id not in self.et_cells_dict.keys():
                logging.error(
                    'read_et_cells_crops(), cell_id %s not found' % cell_id)
                sys.exit()
            cell = self.et_cells_dict[cell_id]
            cell.init_crops_from_row(row, crop_numbers)
            cell.source_file_crop = fn
            cell.crop_names = crop_names
            cell.crop_numbers = crop_numbers
            
            ## List of active crop numbers (i.e. flag is True) in the cell
            cell.crop_num_list = sorted(
                [k for k,v in cell.crop_flags.items() if v])
            self.crop_num_list.extend(cell.crop_num_list)
            
        ## Update list of active crop numbers in all cells
        self.crop_num_list = sorted(list(set(self.crop_num_list)))
    
    def set_cell_cuttings(self, fn, delimiter='\t', skip_rows=2):
        """Extract the mean cutting data from the text file
    
        Args:
            fn (str): file path of the mean cuttings text file
            delimiter (str): file delimiter (i.e. space, comma, tab, etc.)
            skip_rows (str): number of header rows to skip
        """
        logging.info('Setting static cell cuttings')
        with open(fn, 'r') as fp:
            a = fp.readlines()
            
        ## ET Cell ID may not be the first column in older files
        ## Older excel files had ID as the second column in the cuttings tab
        ## Try to find it in the header row
        try:
            cell_id_index = a[1].split(delimiter).index('ET Cell ID')
        except:
            cell_id_index = None
            
        a = a[skip_rows:]
        for i, line in enumerate(a):
            row = line.split(delimiter)
            if cell_id_index is not None:
                cell_id = row[cell_id_index]
            else:
                cell_id = row[0]
            if cell_id not in self.et_cells_dict.keys():
                logging.error(
                    'crop_et_data.static_mean_cuttings(), cell_id %s not found' % cell_id)
                sys.exit()
            cell = self.et_cells_dict[cell_id]
            cell.init_cuttings_from_row(row)
   
    def filter_cell_crops(self, skip_list=[], test_list=[]):
        """Remove ET cells without active crops
    
        Args:
            fn (str): file path  of the ET cell crops text file
            skip_list (list): crop numbers to skip
            test_list (list): crop numbers to test
        """
        if skip_list or test_list:
            logging.info('Filtering ET Cell list based on crop lists')
            logging.info('  Crop skip list: {}'.format(','.join(map(str, skip_list))))
            logging.info('  Crop test list: {}'.format(','.join(map(str, test_list))))
            
            ## Filter main crop number list based on skip and test lists
            self.crop_num_list = [
                crop_num for crop_num in self.crop_num_list
                if ((skip_list and crop_num not in skip_list) or 
                    (test_list and crop_num in test_list))]
            
            ## Get max length of CELL_ID for formatting of log string
            cell_id_len = max([len(cell_id) for cell_id in self.et_cells_dict.keys()])

            ## Remove cells without any active crops
            for cell_id, cell in sorted(self.et_cells_dict.items()):
                if not set(self.crop_num_list) & set(cell.crop_num_list):
                ##if not any(c in self.crop_num_list for c in cell.crop_num_list):
                    logging.debug('  CellID: {1:{0}s} skipping'.format(cell_id_len, cell_id))
                    del self.et_cells_dict[cell_id]
                else:
                    logging.debug(('  CellID: {}').format(cell_id))
   
    def set_static_crop_params(self, crop_params):
        """"""
        logging.info('\nSetting static crop parameters')
        ##print crop_params
        for cell_id in sorted(self.et_cells_dict.keys()):
            cell = self.et_cells_dict[cell_id]
            cell.crop_params = crop_params.copy()
            
    def set_static_crop_coeffs(self, crop_coeffs):
        """"""
        logging.info('Setting static crop coefficients')
        for cell_id in sorted(self.et_cells_dict.keys()):
            cell = self.et_cells_dict[cell_id]
            cell.crop_coeffs = crop_coeffs.copy()

    def set_spatial_crop_params(self, calibration_ws):
        """"""
        logging.info('Setting spatially varying crop parameters')
        cell_id_field = 'CELL_ID'
        crop_dbf_re = re.compile('crop_\d{2}_\w+.dbf$', re.I)
        
        ## Get list of crop parameter shapefiles DBFs
        crop_dbf_dict = dict([
            (int(item.split('_')[1]), os.path.join(calibration_ws, item))
            for item in os.listdir(calibration_ws)
            if crop_dbf_re.match(item)])
            
        ## Filter the file list based on the "active" crops
        for crop_num in crop_dbf_dict.keys():
            if crop_num not in self.crop_num_list:
                try: del crop_dbf_dict[crop_num]
                except: pass
        
        ## DEADBEEF - This really shouldn't be hard coded here
        ## Dictionary to convert shapefile field names to crop parameters
        param_field_dict = {
            'Name':      'name',
            'ClassNum':  'class_number',
            'IsAnnual':  'is_annual',
            'IrrigFlag': 'irrigation_flag',
            'IrrigDays': 'days_after_planting_irrigation',
            'Crop_FW':   'crop_fw', 
            'WinterCov': 'winter_surface_cover_class',
            'CropKcMax': 'kc_max',
            'MAD_Init':  'mad_initial',
            'MAD_Mid':   'mad_midseason',
            'RootDepIni':'rooting_depth_initial',
            'RootDepMax':'rooting_depth_max',
            'EndRootGrw':'end_of_root_growth_fraction_time',
            'HeightInit':'height_initial',
            'HeightMax': 'height_max',
            'CurveNum':  'curve_number',
            'CurveName': 'curve_name',
            'CurveType': 'curve_type',
            'PL_GU_Flag':'flag_for_means_to_estimate_pl_or_gu',
            'T30_CGDD':  't30_for_pl_or_gu_or_cgdd',
            'PL_GU_Date':'date_of_pl_or_gu',
            'CGDD_Tbase':'tbase',
            'CGDD_EFC':  'cgdd_for_efc',
            'CGDD_Term': 'cgdd_for_termination',
            'Time_EFC':  'time_for_efc',
            'Time_Harv': 'time_for_harvest',
            'KillFrostC':'killing_frost_temperature',
            'InvokeStrs':'invoke_stress',
            'CN_Coarse': 'cn_coarse_soil',
            'CN_Medium': 'cn_medium_soil',
            'CN_Fine':   'cn_fine_soil'}
        ## Cuttings values can also be updated spatially
        cutting_field_dict = {
            'Beef_Cut':  'beef_cuttings',
            'Dairy_Cur': 'dairy_cuttings'}
    
        ## Crop parameter shapefiles are by crop, 
        ##   but parameters need to be separated first by ETCell
        ## Process each crop parameter shapefile
        for crop_num, crop_dbf in sorted(crop_dbf_dict.items()):
            logging.debug('    {0:2d} {1}'.format(crop_num, crop_dbf))
            crop_f = DBF(crop_dbf)
            for record in crop_f:
                cell_id = record[cell_id_field]
                for field_name, row_value in dict(record).items():
                    ## DEADBEEF - I really want to skip non-crop param fields
                    ##   but also tell the user if a crop param field is missing
                    try: param_name = param_field_dict[field_name]
                    except: param_name = None
                    try: cutting_name = cutting_field_dict[field_name]
                    except: cutting_name = None
                    if param_name is not None:
                        try:
                            setattr(
                                self.et_cells_dict[cell_id].crop_params[crop_num], 
                                param_name, row_value)
                        except:
                            logging.warning(
                                ('  The spatial crop parameter was not updated\n'+
                                 '    cell_id:    {0}\n    crop_num:   {1}\n'+
                                 '    field_name: {2}\n    parameter:  {3}').format(
                                 cell_id, crop_num, field_name, param_name))
                            raw_input('ENTER')
                    elif cutting_name is not None:
                        try:
                            setattr(self.et_cells_dict[cell_id], cutting_name, row_value)
                        except:
                            logging.warning(
                                ('  The spatial cutting parameter was not updated\n'+
                                 '    cell_id:    {0}\n    crop_num:   {1}\n'+
                                 '    field_name: {2}\n    parameter:  {3}').format(
                                 cell_id, crop_num, field_name, cutting_name))
                            raw_input('ENTER')
                            
class ETCell():
    def __init__(self):
        """ """
    
    def __str__(self):
        """ """
        return '<ETCell {0}, {1} {2}>'.format(
            self.cell_id, self.cell_name, self.refet_id)

    def init_properties_from_row(self, data):
        """ Parse a row of data from the ET cell properties file

        Order of the values:
            ETCellIDs, ETCellNames, RefETIDs, station_lat, station_long,
            station_elevft, station_WHC, station_soildepth, station_HydroGroup,
            aridity_rating, refet_path

        Args:
            data (list): row values

        """
        self.cell_id = data[0]
        self.cell_name = data[1]
        self.refet_id = data[2]    # met_id ??
        self.stn_lat = float(data[3])
        self.stn_lon = float(data[4])
        self.stn_elev = float(data[5])
        self.permeability = float(data[6])
        self.stn_whc = float(data[7])
        self.stn_soildepth = float(data[8])
        self.stn_hydrogroup_str = data[9]
        ## [140822] changed for RioGrande
        #self.stn_hydrogroup = int(data[10])
        self.stn_hydrogroup = int(eval(data[10]))
        self.aridity_rating = float(data[11])
        ## DEADBEEF - RefET path will be build from the ID and format
        ##self.refet_path = data[12]
        ##if len(data) == 14:       # CVP
        ##    self.area = data[13]
        ##elif len(data) == 15:     # truckee
        ##    self.huc = data[13]
        ##    self.huc_name = data[14]
        ##elif len(data) > 13:
        ##    self.cell_lat = float(data[13])
        ##    self.cell_lon = float(data[14])
        ##    self.cell_elev = float(data[15])
        ## DEADBEEF - For now assume station and cell have the same lat/lon/elev
        ##self.cell_lat = float(data[13])
        ##self.cell_lon = float(data[14])
        ##self.cell_elev = float(data[15])
        
        ## Compute air pressure of the station/cell
        self.air_pressure = util.pair_from_elev(0.3048 * self.stn_elev)
        ##self.air_pressure = util.pair_from_elev(0.3048 * self.cell_elev)

    def init_crops_from_row(self, data, crop_numbers):
        """Parse the row of data
        
        There is code in kcb_daily to adjust cgdd_term using the crop flag as a multiplier
        This code is currently commented out and crop_flags are being read in as booleans 

        """
        self.irrigation_flag = int(data[3])
        self.crop_flags = dict(zip(crop_numbers, data[4:].astype(bool)))
        ##self.crop_flags = dict(zip(crop_numbers, data[4:]))
        self.ncrops = len(self.crop_flags)

    def init_cuttings_from_row(self, data):
        """ Parse the row of data """
        ##self.cuttingsLat = float(data[2])
        self.dairy_cuttings = int(data[3])
        self.beef_cuttings = int(data[4])

    def initialize_weather(self, data):
        """Wrapper for setting all refet/weather/climate data"""
        ## Could the pandas dataframes be inherited instead from data
        self.set_refet_data(data.refet)
        self.set_weather_data(data.weather)
        
        ## Process climate arrays
        self.process_climate()
        self.subset_weather_data(data.start_dt, data.end_dt)

    def set_refet_data(self, refet):
        """Read the ETo/ETr data file for a single station using Pandas

        Args:
            refet (dict): RefET parameters from the INI file

        Returns:
            Dictionary of the RefET data, keys are the columns,
                and values are numpy arrays of the data
        """
        logging.debug('\nRead ETo/ETr data')
        refet_path = os.path.join(refet['ws'], refet['format'] % self.refet_id)
        logging.debug('  {0}'.format(refet_path))

        ## Get list of 0 based line numbers to skip
        ## Ignore header but assume header was set as a 1's based index
        skiprows = [i for i in range(refet['header_lines'])
                    if i+1 <> refet['names_line']]
        self.refet_pd = pd.read_table(
            refet_path, engine='python', header=refet['names_line']-1,
            skiprows=skiprows, delimiter=refet['delimiter'])
        logging.debug('  Columns: {}'.format(
            ', '.join(list(self.refet_pd.columns.values))))

        ## Check fields
        for field_key, field_name in refet['fields'].items():
            if field_name is not None and field_name not in self.refet_pd.columns:
                logging.error(
                    ('\n  ERROR: Field "{0}" was not found in {1}\n'+
                     '    Check the {2}_field value in the INI file').format(
                    field_name, os.path.basename(refet_path), field_key))
                sys.exit()
            ## Rename the dataframe fields
            self.refet_pd = self.refet_pd.rename(columns = {field_name:field_key})
        ## Check/modify units
        for field_key, field_units in refet['units'].items():
            if field_units is None:
                continue
            elif field_units.lower() in ['mm/day', 'mm']:
                continue
            else:
                logging.error('\n ERROR: Unknown {0} units {1}'.format(
                    field_key, field_units))
                    
        ## Convert date strings to datetimes
        if refet['fields']['date'] is not None:
            self.refet_pd['date'] = pd.to_datetime(self.refet_pd['date'])
        else:
            self.refet_pd['date'] = self.refet_pd[['year', 'month', 'day']].apply(
                lambda s : datetime.datetime(*s),axis = 1)
        ##self.refet_pd['date'] = pd.to_datetime(self.refet_pd['date'])
        self.refet_pd.set_index('date', inplace=True)
        self.refet_pd['doy'] = [int(ts.strftime('%j')) for ts in self.refet_pd.index]
        
        return True
        ## return refet_pd

    def set_weather_data(self, weather):
        """Read the meteorological/climate data file for a single station using Pandas

        Args:
            met_params (dict): Weater parameters from the INI file

        Returns:
            Dictionary of the RefET data, keys are the columns,
                and values are numpy arrays of the data
        """
        logging.debug('Read meteorological/climate data')

        weather_path = os.path.join(
            weather['ws'], weather['format'] % self.refet_id)
        logging.debug('  {0}'.format(weather_path))

        ## Get list of 0 based line numbers to skip
        ## Ignore header but assume header was set as a 1's based index
        data_skip = [i for i in range(weather['header_lines'])
                     if i+1 <> weather['names_line']]
        self.weather_pd = pd.read_table(
            weather_path, engine='python',
            header=weather['names_line']-1,
            skiprows=data_skip, sep=weather['delimiter'])
        logging.debug('  Columns: {0}'.format(
            ', '.join(list(self.weather_pd.columns.values))))

        ## Check fields
        for field_key, field_name in weather['fields'].items():
            if (field_name is not None and 
                field_name not in self.weather_pd.columns):
                logging.error(
                    ('\n  ERROR: Field "{0}" was not found in {1}\n'+
                     '    Check the {2}_field value in the INI file').format(
                    field_name, os.path.basename(weather_path), field_key))
                sys.exit()
            ## Rename the dataframe fields
            self.weather_pd = self.weather_pd.rename(
                columns = {field_name:field_key})
        ## Check/modify units
        for field_key, field_units in weather['units'].items():
            if field_units is None:
                continue
            elif field_units.lower() in ['c', 'mm', 'm/s', 'mj/m2', 'mj/m^2', 'kg/kg']:
                continue
            elif field_units.lower() == 'k':
                self.weather_pd[field_key] -= 273.15
            elif field_units.lower() == 'f':
                self.weather_pd[field_key] -= 32
                self.weather_pd[field_key] /= 1.8
            elif field_units.lower() == 'in*100':
                self.weather_pd[field_key] *= 0.254
            elif field_units.lower() == 'in':
                self.weather_pd[field_key] *= 25.4
            elif field_units.lower() in ['w/m2', 'w/m^2']:
                self.weather_pd[field_key] *= 0.0864
            else:
                logging.error('\n ERROR: Unknown {0} units {1}'.format(
                    field_key, field_units))
                    
        ## Convert date strings to datetimes
        if weather['fields']['date'] is not None:
            self.weather_pd['date'] = pd.to_datetime(self.weather_pd['date'])
        else:
            self.weather_pd['date'] = self.weather_pd[['year', 'month', 'day']].apply(
                lambda s : datetime.datetime(*s),axis = 1)
        ##self.weather_pd['date'] = pd.to_datetime(self.weather_pd['date'])
        self.weather_pd.set_index('date', inplace=True)
        self.weather_pd['doy'] = [int(ts.strftime('%j')) for ts in self.weather_pd.index]
                    
        ## Scale wind height to 2m if necessary
        if weather['wind_height'] <> 2:
            self.weather_pd['wind'] *= (
                4.87 / np.log(67.8 * weather['wind_height'] - 5.42))
                
        ## Add snow and snow_depth if necessary
        if 'snow' not in self.weather_pd.columns:
            self.weather_pd['snow'] = 0
        if 'snow_depth' not in self.weather_pd.columns:
            self.weather_pd['snow_depth'] = 0

        ## Calculate Tdew from specific humidity
        ## Convert station elevation from feet to meters
        if ('tdew' not in self.weather_pd.columns and 
            'q' in self.weather_pd.columns):
            self.weather_pd['tdew'] = util.tdew_from_ea(util.ea_from_q(
                self.air_pressure, self.weather_pd['q'].values))

        ## Compute RH from Tdew and Tmax
        if ('rh_min' not in self.weather_pd.columns and 
            'tdew' in self.weather_pd.columns and 
            'tmax' in self.weather_pd.columns):
            ## For now do not consider SVP over ice
            ## (it was not used in ETr or ETo computations, anyway)
            self.weather_pd['rh_min'] = 100 * np.clip(
                util.es_from_t(self.weather_pd['tdew'].values) / 
                util.es_from_t(self.weather_pd['tmax'].values), 0, 1)
        
        ## Set CO2 correction values to 1 if they are not in the data
        ##if 'co2_grass' not in self.weather_pd.columns:
        ##    self.weather_pd['co2_grass'] = 1
        ##if 'co2_trees' not in self.weather_pd.columns:
        ##    self.weather_pd['co2_trees'] = 1
        ##if 'co2_c4' not in self.weather_pd.columns:
        ##    self.weather_pd['co2_c4'] = 1
        
        return True
        ## return weather_pd

    def process_climate(self):
        """ 
        
        compute long term averages (DAY LOOP)
            adjust and check temperature data
            process alternative TMax and TMin
        fill in missing data with long term doy average (DAY LOOP)
            Calculate an estimated depth of snow on ground using simple melt rate function))
            compute main cumGDD for period of record for various bases for constraining earliest/latest planting or GU
            only Tbase = 0 needs to be evaluated (used to est. GU for alfalfa, mint, hops)
        compute long term mean cumGDD0 from sums (JDOY LOOP)

        AltTMaxArray, AltTMinArray in code has to do with when future climate
        gets so much warmer that annuals are starting too soon, in this case,
        they used the historical, ie, AltTMaxArray, AltTMinArray == historical,
        so IGNORE   

        Also lots of missing data substitution stuff going on, ignore, this
        should be taken care of outside of process
        """
       
        ## Initialize the climate dataframe
        self.climate_pd = self.weather_pd[
            ['doy', 'tmax', 'tmin', 'snow', 'snow_depth']].copy()

        ## Adjust T's downward if station is arid
        if self.aridity_rating > 0:
            ## Interpolate value for aridity adjustment
            aridity_adj = [0., 0., 0., 0., 1., 1.5, 2., 3.5, 4.5, 3., 0., 0., 0.]
            month = np.array([dt.month for dt in self.weather_pd.index])
            day = np.array([dt.day for dt in self.weather_pd.index])
            moa_frac = np.clip((month + (day - 15) / 30.4), 1, 11)
            arid_adj = np.interp(moa_frac, range(len(aridity_adj)), aridity_adj)
            arid_adj *= self.aridity_rating / 100.
            self.climate_pd['tmax'] -= arid_adj
            self.climate_pd['tmin'] -= arid_adj
            del month, day, arid_adj

        ## T30 stuff, done after temperature adjustments above
        self.climate_pd['tmean'] = self.climate_pd[["tmax", "tmin"]].mean(axis=1)
        self.climate_pd['t30'] = pd.rolling_mean(
            self.climate_pd['tmean'], window=30, min_periods=1)
        
        ## Build cumulative T30 over period of record
        main_t30_lt = np.array(self.climate_pd[['t30', 'doy']].groupby('doy').mean()['t30'])
        
        ## Compute GDD for each day
        self.climate_pd['cgdd'] = self.climate_pd['tmean']
        self.climate_pd.ix[self.climate_pd['tmean'] <= 0, 'cgdd'] = 0
        # Tbase(ctCount) -- have no idea what ctCount value should be, since this
        # is before start of CropCycle & each crop has own Tbase value in
        # crop_parameters.py, use 0.0 for now, since appears may be ctCount
        #  Based on previous comment, assume Tbase = 0.0
        ## DEADBEEF - Uncomment if tbase is set to anything other than 0
        ##tbase = 0.0
        ##self.climate_pd.ix[self.climate_pd['tmean'] > 0, 'ggdd'] -= tbase
        
        ## Compute cumulative GDD for each year
        self.climate_pd['cgdd'] = self.climate_pd[['doy', 'cgdd']].groupby(
            self.climate_pd.index.map(lambda x: x.year)).cgdd.cumsum()
        ## DEADBEEF - Compute year column then compute cumulative GDD
        ##self.climate_pd['year'] = [dt.year for dt in self.climate_pd.index]
        ##self.climate_pd['cgdd'] = self.climate_pd[['year', 'doy', 'gdd']].groupby('year').gdd.cumsum()
        
        ## Compute mean cumulative GDD for each DOY
        main_cgdd_0_lt = np.array(self.climate_pd[['cgdd', 'doy']].groupby('doy').mean()['cgdd'])
          
        ## Revert from indexing by I to indexing by DOY (for now)
        ## Copy DOY 1 value into DOY 0
        main_t30_lt = np.insert(main_t30_lt, 0, main_t30_lt[0])
        main_cgdd_0_lt = np.insert(main_cgdd_0_lt, 0, main_cgdd_0_lt[0])
        
        ##
        self.climate = {}           
        self.climate['main_t30_lt'] = main_t30_lt
        self.climate['main_cgdd_0_lt'] = main_cgdd_0_lt

        ## Calculate an estimated depth of snow on ground using simple melt rate function))   
        if np.any(self.climate_pd['snow']):
            for i, doy in self.weather_pd['doy'].iteritems():
                ## Calculate an estimated depth of snow on ground using simple melt rate function
                snow = self.climate_pd['snow'][i]
                snow_depth = self.climate_pd['snow_depth'][i]
                ## Assume a settle rate of 2 to 1
                snow_accum += snow * 0.5 #' assume a settle rate of 2 to 1
                ## 4 mm/day melt per degree C
                snow_melt = max(4 * self.climate_pd['tmax'][i], 0.0)
                snow_accum = max(snow_accum - snow_melt, 0.0)
                snow_depth = min(snow_depth, snow_accum)
                self.weather_pd['snow_depth'][i] = snow_depth
        return True
        ## return climate_pd

    def subset_weather_data(self, start_dt=None, end_dt=None): 
        """Subset the dataframes based on the start and end date"""
        if start_dt is not None:
            self.refet_pd = self.refet_pd[self.refet_pd.index >= start_dt]
            self.weather_pd = self.weather_pd[self.weather_pd.index >= start_dt]
            self.climate_pd = self.climate_pd[self.climate_pd.index >= start_dt]
        if end_dt is not None:
            self.refet_pd = self.refet_pd[self.refet_pd.index <= end_dt]
            ##self.refet_pd = self.refet_pd.ix[self.refet_pd.index <= end_dt]
            self.weather_pd = self.weather_pd[self.weather_pd.index <= end_dt]
            self.climate_pd = self.climate_pd[self.climate_pd.index <= end_dt]
        return True
         
if __name__ == '__main__':
    pass
