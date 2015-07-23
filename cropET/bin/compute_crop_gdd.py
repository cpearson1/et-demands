import logging

import util

def compute_crop_gdd(data, crop, foo, foo_day):
    """Compute crop growing degree days

    """
    ##logging.debug('compute_crop_gdd()')

    ## Calculate 30 day ETr each year
    ## Shift entries in 30 day array to add today's ETref
    etref_lost = 0.0
    if foo_day.sdays > 30:
        #ETreflost = ETref_array(1)
        #For idx = 1 To 29 #' idx = 1 is 30 days ago
        etref_lost = foo_day.etref_array[0]
        for idx in range(29):   #' idx = 1 is 30 days ago
            foo_day.etref_array[idx] = foo_day.etref_array[idx + 1]
        foo_day.etref_array[29] = foo_day.etref
        foo.etref_30 = foo.etref_30 + (foo_day.etref - etref_lost) / 30.
    else:
        foo_day.etref_array[foo_day.sdays-1] = foo_day.etref
        foo.etref_30 = (foo.etref_30 * (foo_day.sdays - 1) + foo_day.etref) / foo_day.sdays
        #foo.etref_30 = (foo.etref_30 * (foo_day.sdays) + foo_day.etref) / (foo_day.sdays + 1)
    #print 'ETref30', foo.etref_30, foo_day.sdays, foo_day.etref

    # reset CGDD if new year
    # for all crops, but winter grain, reset CGDD counter on cropGDDTriggerDoy (formerly hard wired to Jan 1 or Oct 1)
    # ctCount = 13 and 14 are winter grain (irrigated and nonirrigated)

    #' winter grain '<------ specific value for crop number, changed to two ww crops Jan 07
    #If ctCount = 13 Or ctCount = 14 Or ccName.Equals("WINTER WHEAT") Then 
    #if crop.curve_number in [13,14] or crop.curve_name == 'WINTER WHEAT':
    if crop.class_number in [13,14] or 'WINTER' in crop.curve_name:
        if (foo.lDoy < crop.crop_gdd_trigger_doy and
            foo_day.doy >= crop.crop_gdd_trigger_doy):
            foo.cgdd = 0.0
            foo.doy_start_cycle = 0    #' DOY 0 - reset planting date also
            foo.real_start = False   #' April 12, 2009 rga
            foo.in_season = False    #' July 30, 20120 dlk
            #' PrintLine(lfNum, "Setting winter grain off " & Chr(9) & dailyDates(sdays - 1) & ", doy " & Chr(9) & doy)
        foo.lDoy = foo_day.doy
    else:
        if (foo.lDoy > crop.crop_gdd_trigger_doy + 199 and
            foo_day.doy < crop.crop_gdd_trigger_doy + 199):
            foo.cgdd = 0.0
            foo.doy_start_cycle = 0    #' DoY 0 - reset planting date also
            foo.real_start = False   #' April 12, 2009 rga
            foo.in_season = False    #' July 30, 20120 dlk
        foo.lDoy = foo_day.doy
    logging.debug(
        ('compute_crop_gdd(): ETref30 %.6f  sdays %s  ETref %.6f  ETref_lost %.6f') %
        (foo.etref_30, foo_day.sdays, foo_day.etref, etref_lost))
    logging.debug(
        ('compute_crop_gdd(): doy_start_cycle %s  crop_curve_number %s  '+
         'crop_class_num %s') %
        (foo.doy_start_cycle, crop.curve_number, crop.class_number))
    logging.debug('compute_crop_gdd(): in_season %s' % (foo.in_season))

    # Calculate CGDD since trigger date

    # Only needed if a crop
    if crop.curve_number > 0:    
        # use general GDD basis except for corn (crop types 7 thru 10), which require 86-50 method.
        # evalute winter grain separately because of penalties during winter
        # Development of winter grain is followed through winter,
        # beginning with an assumed October 1 planting in Northern hemisphere
        # Any periods during winter with favorable growing conditions are assumed to advance development of winter grain crop subject to following conditions:
        #   Initial GDD calculation is TMean - Tbase if TMean > Tbase, or 0 otherwise.
        #   GDD is set to zero if TMin for that day is less than -3 C to actCount for negative impacts of freezing.
        #   In addition, subtract 10 GDD from daily GDD if TMin of previous day < -5 C to actCount for retardation (stunning) that carries over into next day.
        #   Minimum adjusted GDD for any day is 0.
        #   If TMin for day is < -25 C (very cold temperature) and no snow cover, burning of leaves is assumed to occur and CGDD is reduced.
        #      On first day following -25 C TMin, CGDD prior to day is reduced by 30%.

        if (crop.class_number in [13,14] or
            crop.curve_name == 'WINTER WHEAT'):
            ## Winter wheat or winter grain
            foo.gdd = 0.0
            if foo_day.tmin < -4.0:
                # No growth if <-3C (was -3, now -4)
                foo.gdd = 0.0
            elif foo_day.tmean > crop.tbase:
                # Simple method for all other crops
                foo.gdd = foo_day.tmean - crop.tbase
            foo.gdd = foo.gdd - foo.penalty
            #If penalty > 0 Then PrintLine(lfNum, "Winter grain penalty on " & getDmiDate(dailyDates(sdays - 1)) & " is " & penalty & " GDD with penalty is " & GDD)
            foo.penalty = 0.0
            foo.gdd = max(foo.gdd, 0.0)
            foo.cgdd = foo.cgdd + foo.gdd - foo.cgdd_penalty
            foo.cgdd_penalty = 0.0
            foo.cgdd = max(0.0, foo.cgdd)
            #print '->', foo.gdd, foo.penalty

            # Set up for tommorrow's penalties for winter grain
            if foo_day.tmin < -10:
                foo.penalty = 5.0
            else:
                # Set up for tomorrow's penalty for low TMin today (was 10), TMin was -5
                foo.penalty = 0.0
            if foo_day.tmin < -25:
                # Burn back on winter grain from severe cold if no snow cover
                # Was 0.3
                if foo_day.snow_depth <= 0:
                    foo.cgdd_penalty = foo.cgdd * 0.1
        elif crop.tbase < 0:
            # Corn
            tmaxl = foo_day.tmax
            tminl = foo_day.tmin
            # TMax and TMin are subject to Tbase limits for corn
            if foo_day.tmax > 30:
                tmaxl = 30
            # And to maximum limits for corn
            if foo_day.tmin > 30:
                tminl = 30
            # sub tbase since it is artificially neg. for corn as a flag
            if foo_day.tmax < - crop.tbase:
                tmaxl = -crop.tbase
            if foo_day.tmin < - crop.tbase:
                tminl = -crop.tbase
            tmeanl = 0.5 * (tmaxl + tminl)
            # Add tbase since it is artificially set negative as an indicator
            foo.cgdd = foo.cgdd + tmeanl + crop.tbase
        elif foo_day.tmean > crop.tbase:
            # Simple method for all other crops
            foo.gdd = foo_day.tmean - crop.tbase
            foo.cgdd = foo.cgdd + foo.gdd

    logging.debug('compute_crop_gdd(): GDD %.6f  CGDD %.6f' % (foo.gdd, foo.cgdd))
