#!/usr/bin/env python
import datetime
import logging
import math
import os
import re
import sys

import numpy as np

import crop_et_data
import compute_crop_et
from initialize_crop_cycle import InitializeCropCycle
import util

class DayData:
    def __init__(self):
        """ """
        ## Used in compute_crop_gdd(), needs to be persistant during day loop
        self.etref_array = np.zeros(30)

def crop_cycle(data, et_cell, start_dt, end_dt, basin_id, output_ws):
    """"""
    ## Following is for one crop grown back to back over entire ETr sequence
    ##
    ## do bare soil first, before looping through crops
    ## current curve file has 60 curves, so 44 is not correct relative to coefficients
    ##'''
    ##   ' start with crop type 44 (bare soil, winter mulch) and run through last crop first '<------ specific value for crop number
    ##   ' this is done to compute 'winter covers', which are bare soil, mulch and dormant turf,
    ##   ' before any crops are processed.  Bare soil is "crop" no. 44.
    ##'''
    #### no curve for bare soil
    ##ctCount = 43  # bare soil
    ##ctCount = 1  # bare soil
    
    ##logging.debug('in crop_cycle()')

    ## crop loop through all crops, doesn't include bare soil??
    for crop_num, crop in sorted(et_cell.crop_params.items()):
        ## Check to see if crop/landuse is at station
        if not et_cell.crop_flags[crop_num]:
            logging.debug('Crop %s %s' % (crop_num, crop))
            logging.debug('  NOT USED')
            continue
        else:
            logging.info('Crop %s %s' % (crop_num, crop))
            
        logging.debug(
            'crop_day_loop():  Curve %s %s  Class %s  Flag %s' %
            (crop.curve_number, crop.curve_name,
             crop.class_number, et_cell.crop_flags[crop_num]))
        ##logging.debug('  Crop:  {0} {1}'.format(crop_num, crop))
        ##logging.debug('  Curve: {0} {1}'.format(
        ##    crop.curve_number, crop.curve_name))
        ##logging.debug('  Class: {}'.format(crop.class_number))
        ##logging.debug('  Flag:  {}'.format(et_cell.crop_flags[crop_num]))

        logging.debug('  GDD trigger DOY: {}'.format(crop.crop_gdd_trigger_doy))

        ## 'foo' is holder of all these global variables for now
        foo = InitializeCropCycle()

        ## First time through for crop, load basic crop parameters and process climate data
        foo.crop_load(data, et_cell, crop)

        ## Open output file for each crop and write header
        output_name = '%s_%s.dat' % (et_cell.cell_id, crop.class_number)
        output_path = os.path.join(output_ws, output_name)
        fmt = '%10s %3s %9s %9s %9s %9s %9s %9s %9s %5s %9s %9s\n' 
        header = (
            '#     Date','DOY','PMETo','Pr.mm','T30','ETact',
            'ETpot','ETbas','Irrn','Seasn','Runof','DPerc')
        output_f = open(output_path, 'w')
        output_f.write(fmt % header)

        ## 
        crop_day_loop(
            data, et_cell, crop, foo, start_dt, end_dt, output_f)

        ## Close output file
        output_f.close()

def crop_day_loop(data, et_cell, crop, foo, start_dt=None, end_dt=None,
                  output_f=None):
    """

    Args:
        data ():
        et_cell ():
        crop ():
        foo ():
        nsteps (int):
        start_dt (date):
        end_dt (date):
        output_f (): 

    Returns:
        None
    """
    ##logging.debug('crop_day_loop()')
    foo_day = DayData()

    ## Originally in ProcessClimate() in vb code
    if data.refet_type > 0:
        refet_array = et_cell.refet['ASCEPMStdETr']
    else:
        refet_array = et_cell.refet['ASCEPMStdETo']

    ## Build a mask of valid dates
    date_mask = (
        (et_cell.refet['Dates'] >= start_dt) and
        (et_cell.refet['Dates'] <= end_dt))
 
    for i, step_dt in enumerate(et_cell.refet['Dates']):
        step_doy = int(step_dt.strftime('%j'))
        logging.debug('\ncrop_day_loop(): DOY %s  Date %s' % (step_doy, step_dt))
        if not date_mask[i]:
            continue
        ##if start_dt is not None and step_dt < start_dt:
        ##    continue
        ##elif end_dt is not None and step_dt > end_dt:
        ##    continue

        ## Log RefET values at time step 
        logging.debug(
            'crop_day_loop(): PPT %.6f  Wind %.6f  Tdew %.6f' % 
            (et_cell.refet['Precip'][i], et_cell.refet['Wind'][i], 
             et_cell.refet['TDew'][i]))
        logging.debug(
            'crop_day_loop(): ETo %.6f  ETr %.6f  ETref %.6f' % 
            (et_cell.refet['ASCEPMStdETo'][i], et_cell.refet['ASCEPMStdETr'][i], 
             refet_array[i]))

        ## Log climate values at time step         
        logging.debug(
            'crop_day_loop(): tmax %.6f  tmin %.6f  tmean %.6f  t30 %.6f' %
            (et_cell.climate['tmax_array'][i], et_cell.climate['tmin_array'][i], 
             et_cell.climate['tmean_array'][i], et_cell.climate['t30_array'][i]))
        logging.debug(
            'crop_day_loop(): precip %.6f' % et_cell.climate['precip'][i])

        ## At very start for crop, set up for next season
        if not foo.in_season and foo.crop_setup_flag:
            foo.setup_crop(crop)

        ## At end of season for each crop, set up for nongrowing and dormant season
        if not foo.in_season and foo.dormant_setup_flag:
            logging.debug(
                'crop_day_loop(): in_season[%s]  crop_setup[%s]  dormant_setup[%s]' % 
                (foo.in_season, foo.crop_setup_flag, foo.dormant_setup_flag))
            foo.setup_dormant(data, et_cell, crop)
        logging.debug(
            'crop_day_loop(): in_season[%s]  crop_setup[%s]  dormant_setup[%s]' % 
            (foo.in_season, foo.crop_setup_flag, foo.dormant_setup_flag))

        foo_day.sdays = i + 1
        foo_day.doy = step_doy
        foo_day.year = step_dt.year
        foo_day.month = step_dt.month
        foo_day.day = step_dt.day
        foo_day.date = et_cell.refet['Dates'][i]
        foo_day.tmax_orig = et_cell.refet['TMax'][i]
        foo_day.tdew = et_cell.refet['TDew'][i]
        foo_day.wind = et_cell.refet['Wind'][i]
        ## DEADBEEF - Why have 2 wind variables that are the same?
        ##   U2 is at 2m, but wind doesn't have a height passed in
        foo_day.u2 = foo_day.wind 
        foo_day.etref = refet_array[i]
        foo_day.tmean = et_cell.climate['tmean_array'][i]
        foo_day.tmin = et_cell.climate['tmin_array'][i]
        foo_day.tmax = et_cell.climate['tmax_array'][i]
        foo_day.snow_depth = et_cell.climate['snow_depth'][i]
        foo_day.t30 = et_cell.climate['t30_array'][i]
        foo_day.precip = et_cell.climate['precip'][i]

        ## DEADBEEF - Why make copies?
        foo_day.cgdd_0_lt = np.copy(et_cell.climate['main_cgdd_0_lt'])
        #foo_day.t30_lt = np.copy(et_cell.climate['main_t30_lt'])

        ## Compute RH from Tdew
        ## DEADBEEF - Why would tdew or tmax_original be < -90?
        if foo_day.tdew < -90 or foo_day.tmax_orig < -90:
            foo_day.rh_min = 30.0
        else:
            es_tdew = util.aFNEs(foo_day.tdew)
            # For now do not consider SVP over ice
            # (it was not used in ETr or ETo computations, anyway)
            es_tmax = util.aFNEs(foo_day.tmax_orig) 
            foo_day.rh_min = min(es_tdew / es_tmax * 100, 100)
                
        ## Calculate Kcb, Ke, ETc
        #If Not compute_crop_et(T30) Then Return False
        compute_crop_et.compute_crop_et(
            data, et_cell, crop, foo, foo_day)

        ## Compute NIWR at daily time step and write out

        ## Write vb-like output file for comparison
        if output_f:
            tup = (step_dt, step_doy, foo_day.etref, foo_day.precip, 
                   foo_day.t30, foo.etc_act, foo.etc_pot,
                   foo.etc_bas, foo.irr_sim, foo.in_season, foo.sro, foo.dpr)
            fmt = '%10s %3s %9.3f %9.3f %9.3f %9.3f %9.3f %9.3f %9.3f %5d %9.3f %9.3f\n'
            output_f.write(fmt % tup)

        ## Write final output file variables to DEBUG file
        logging.debug(
            ('crop_day_loop(): ETref  %.6f  Precip %.6f  T30 %.6f') %
            (foo_day.etref, foo_day.precip, foo_day.t30))
        logging.debug(
            ('crop_day_loop(): ETact  %.6f  ETpot %.6f   ETbas %.6f') %
            (foo.etc_act, foo.etc_pot, foo.etc_bas))
        logging.debug(
            ('crop_day_loop(): Irrig  %.6f  Runoff %.6f  DPerc %.6f') %
            (foo.irr_sim, foo.sro, foo.dpr))

def main():
    """ """
    pass

if __name__ == '__main__':
    main()
