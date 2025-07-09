
{
//HISTORY 
	======= 
	Date                       By                          Version                   Description 
	----------	---------------------------------	---------------------    -----------------------------------------
	2024-01-13	      Gary Armani(ucgary@gmail.com) 	    V1    	          build indicator first, then strategy. not the same as tradingview indicator "Order Block Finder". 
	2024-01-15	      Gary Armani(ucgary@gmail.com) 	    V1    	          build strategy, added session time,
	2024-04-18	      Gary Armani(ucgary@gmail.com) 	    V1    	          add limit order( usemarketorder parameter ) 
	2024-10-10	      Gary Armani(ucgary@gmail.com) 	    V2				   build from new version of !order block finder indicator 
	2025-02-19	      Gary Armani(ucgary@gmail.com) 	    V2	              add max stop loss and buy/sell at retracement.
	2025-02-20	      Gary Armani(ucgary@gmail.com) 	    V2		          add option:disablee risk reward
}
//strategy('Order Block Finder', overlay=true,process_orders_on_close = true,calc_on_every_tick = true,pyramiding = 1000)
// tradestation does not support DisplayName/Title in strategy. for the consistance, only use tooltip
{
2025-02-19
1, add a maximum stop loss feature, so if loss exceeds "X" number of dollars, the position will close.When this feature is checked on, whichever hits first, ATR stop loss or Maximum $ stop loss will trigger.
2, changes the entry placement. When all of the criteria are met, I would like to have the current market order changed to a limit order, placed at "X" % retracement to the OB location.

 
//
I would like to add EMA to strategy, so that Long orders are only entered if above ema, 
and Short orders are only entered below EMA. 
Also, would like to replace current stop loss with ATR. The ATR should have adjustable length and Multiplier, as shown in the screenshot.

}
Inputs:
TradeStartTime( 0900 )[tooltip="Start time"],  //Start time
TradeExitTime( 0900 )[tooltip="End time"], //End time
ClosePosition_Friday( true )[tooltip="all positions are closed on Friday at 16:45 EST before the market closes. "],  //
Friday_ClosePositionTime( 1645 )[tooltip="the time format is hhmm,  for example 1645 means 16:45"]  ,// 
NumberofShares( 1 )[tooltip="how many contracts per trade"],    //
Enable_EMA( true )[tooltip="Long orders are only entered if above ema, and Short orders are only entered below EMA. "], // 
EMA_Length( 50 )[tooltip="EMA length , for Enable_EMA option"],  // 
Enable_ATR_stop( true )[tooltip="The ATR should have adjustable length and Multiplier"],  //
ATR_Length( 10 )[tooltip="Average True Range Length.  Enter the number of bars to use in the moving average of true range. "],
ATR_Multiplier( 3 )[Tooltip="Number of Average True Ranges.  Enter the number of average true ranges at which to trail the stop order."], //
bool isBull( true )[tooltip="Take Buy Positon"],//  = input.bool(true,"Take Buy Positon")
bool isBear( true )[tooltip="Take Sell Positon"], // =  input.bool(true,"Take Sell Positon")
bool EnableRR(true)[tooltip="Enable risk reward"],  
double rr( 2 )[tooltip="Risk Reward"],  //  =  input.float(2,"Risk Reward",minval = 1)
bool useONe( true )[tooltip="Use trail Stoploss on next trade"], //=  input.bool(true,"Use trail Stoploss on next trade")
bool useVO( true )[tooltip="Use Volume Oscillator"],// =  input.bool(true,"Use Volume Oscillator")
bool useBB( true )[tooltip="Use Bollinger Bands"],// =  //input.bool(true,"Use Bollinger Bands",inline = "kdjf")
double varbb( 20 )[tooltip="threshhold of bollinger bands filter"], //=  input.float(20,"",inline = "kdjf")
// group_sess = "----------------------- Session -----------------------"
// tradestation do not supports set timezone. tradestation use local or exchange.
// isCurstomSession = input.bool(false,"",inline = "session1",group = group_sess,tooltip = "Set Custom time zone if you not set then it will take chart timezone automatic")
// sessionTimeZone = input.string("UTC","Set Tmezone",inline="session1",group = group_sess,options=["UTC","America/New_York","America/Los_Angeles","America/Chicago","America/Phoenix","America/Toronto","America/Vancouver","America/Argentina/Buenos_Aires","America/El_Salvador","America/Sao_Paulo","America/Bogota","Europe/Moscow","Europe/Athens","Europe/Berlin","Europe/London","Europe/Madrid","Europe/Paris","Europe/Warsaw","Australia/Sydney","Australia/Brisbane","Australia/Adelaide","Australia/ACT","Asia/Almaty","Asia/Ashkhabad","Asia/Tokyo","Asia/Taipei","Asia/Singapore","Asia/Shanghai","Asia/Seoul","Asia/Tehran","Asia/Dubai","Asia/Kolkata","Asia/Hong_Kong","Asia/Bangkok","Pacific/Auckland","Pacific/Chatham","Pacific/Fakaofo","Pacific/Honolulu"])
// 2023-1-13 ignore the lins below,  it is session backgroud, tradestation do not support background color
// sessClr  =  input.color(#ff52521c,"",group = group_sess,inline = 'session1')
// Session1        = input.session(title="Session Input", defval="0939-0230",inline="s1",group = group_sess)
// isInSession = na(time(timeframe.period, Session1 + ":1234567",isCurstomSession ? sessionTimeZone : syminfo.timezone)) == false 
// bgcolor(isInSession ? sessClr : na,title = "Session Backgraoud Color")
int mintickinput( 1 )[tooltip="Entry Tick Below/Above"], // tick //  // =  input.int(1,"Entry Tick Below/Above",minval =  0)*syminfo.mintick
string colors( "DARK" )[tooltip="Color Scheme: DARK or BRIGHT "],  // = input.string(title='Color Scheme', defval='DARK', options=['DARK', 'BRIGHT'])
int periods( 5 )[tooltip="Relevant Periods to identify OB"],  // = input(5, 'Relevant Periods to identify OB')  // Required number of subsequent candles in the same direction to identify Order Block
double threshold( 0 )[tooltip="Min. Percent move to identify OB"],  // = input.float(0.0, 'Min. Percent move to identify OB', step=0.1)  // Required minimum % move (from potential OB close to last subsequent candle to identify Order Block)
bool usewicks( false )[tooltip="Use whole range [High/Low] for OB marking?"],// = input(false, 'Use whole range [High/Low] for OB marking?')  // Display High/Low range for each OB instead of Open/Low for Bullish / Open/High for Bearish
bool showbull( true )[tooltip="Show latest Bullish Channel?"],// = input(true, 'Show latest Bullish Channel?')  // Show Channel for latest Bullish OB?
bool showbear( true )[tooltip="Show latest Bearish Channel?"],// = input(true, 'Show latest Bearish Channel?')  // Show Channel for latest Bearish OB?
//bool showdocu(false)[tooltip="Show Label for documentation tooltip?"],// = input(false, 'Show Label for documentation tooltip?')  // Show Label which shows documentation as tooltip?
// tradestation do not support table/panel, maybe need to ignore ... 
//bool info_pan(false)[tooltip="Show Latest OB Panel?"],// = input(false, 'Show Latest OB Panel?')  // Show Info Panel with latest OB Stats
//
int shortlen( 7 )[tooltip="Short Length"], // = input.int(7, minval=1, title = "Short Length",group = grosc)
int longlen( 13 )[tooltip="Long Length"],  // = input.int(13, minval=1, title = "Long Length",group = grosc)
//------------------------------------------------------------------------------
//bolling bands Settings
//------------------------------------------------------------------------------
int length( 14 )[tooltip="the number of bars to use in the calculation of the Bollinger bands. Bollinger Bands Breakout Oscillator "],  // Bollinger Bands Breakout Oscillator //  = input(14,group = grbb)
int mult( 1 )[tooltip="Number of Standard Deviations. Bollinger Bands Breakout Oscillator "], // Bollinger Bands Breakout Oscillator //   = input(1.,group = grbb)
double src( close ),  //Bollinger Bands Breakout Oscillator //    = input(close,group = grbb)
// 20241010
bool enable_modify_stop_loss_candle( true )[tooltip="When criteria below (below_BB_Basis,Fifth_Candle_Above_BB_Upper)  are met, modify stop loss candle close below 50% of the Order Block Range. Bullish Order Block range defined as... Low: lower of either the low of OB candle or the low of any wicks below the OB candle and High: close of 5th candle in series following OB"],

//bool below_BB_Basis(true)[tooltip="Bullish order block candle closing price must be below Bollinger Band Basis Band"],
int BB_Length( 14 ) [
		DisplayName = "BB_Length", 
		ToolTip = "Enter the number of bars to use in the calculation of the Bollinger bands."],
double NumDevsUp( 1 ) [
		DisplayName = "NumDevsUp", 
		ToolTip = "Number of Standard Deviations Up.  Enter the number of standard deviations to use in the calculation of the upper Bollinger band."],	
double NumDevsDn( -1 ) [
		DisplayName = "NumDevsDn", 
		ToolTip = "Number of Standard Deviations Down.  Enter the number of standard deviations to use in the calculation of the lower Bollinger band."],
bool Enable_maximum_stop_loss( false )[tooltip="maximum stop loss feature, so if loss exceeds X number of dollars, the position will close."], //	
bool PositionBasis( false ) [DisplayName = "PositionBasis", ToolTip = 
	 "Enter true if currency amounts (profit targets, stops, etc.) are for the entire position;  enter false if currency amounts are per share or per contract."], 
double	Amount( 1000 ) [DisplayName = "Amount", ToolTip = 
	 "Enter the amount of the stop loss (Total position amount if PositionBasis is true; amount per share if PositionBasis is set to false)"] ,
bool Place_at_Retracement( false )[tooltip=" changes the entry placement. When all of the criteria are met, I would like to have the current market order changed to a limit order,"],   // "X" % retracement 
double Place_at_x_percent( 50 )[tooltip="placed at X % retracement to the OB location."]; // 	
//int Fifth_Candle_Above_BB_Upper(5)[tooltip="if it is set to 0, this function is disabled. Fifth candle following bullish order block candle must close higher than the Bollinger Bands Upper Band"];

// 20241010 end		
var:
// 20250219 entry at retracement
bool longSignalstatus1(false),
double longSignalPrice1(0),
bool shortSignalstatus1(false),
double shortSignalPrice1(0),
//
bool exitOnFridayCloseFlag(false),
ATRCalc( 0 ),
ATRCalcFix( 0 ),
PosLow( 0 ),
PosHigh( 0 ),
double emaValForEntry(0),
bool useMarketOrder(true),
bool isSessionOut(false),
cc(0),
TT( 0 ),
mp(0),
Entry_Price(0),
StopLoss_Price(0),
StopLoss_Price2(0),
Target_Price(0),  		
// 20241010
bool modify_stop_loss_candle_flag(false),
double modify_stop_loss_candle_50pct(0),
double Avg( 0 ),
double SDev( 0 ),
double LowerBand( 0 ),
double UpperBand( 0 ),
double longStopRangeMax(0),
double longStopRangemin(0),
double longStopRangePct50(0),  //
double shortStopRangeMax(0),
double shortStopRangeMin(0),
double shortStopRangePct50(0), 
double longstopPrice(0),
double shortstopPrice(0),
// 20241010 end						 
int iVal(0),
int jVal(0),
double iCnt(0),
double cumVol(0),   
double AnyVol( 0 ),
double shortVal(0),
double longVal(0),
double osc(0),
bool isVOBull(false),
bool isVOBear(false),
double emaVal(0),
double upperVal(0),
double lowerVal(0),
double stdev(0),
double bull(0),
double bear(0),
double bull_den(0),
double bear_den(0),
bool isBullBB(false),
bool isBearBB(false),
//
int ob_period(0),
double absmove(0),
bool relmove(false),
//
bool bullishOB(false),
bool bearishOB(false),
int upcandles(0),
int downcandles(0),
int bullcolor(Darkgray),
int bearcolor(Darkgray),
bool OB_bull(false),
bool OB_bear(false),
double OB_bull_high(0),
double OB_bull_low(0),
double OB_bull_avg(0),
double OB_bear_high(0),
double OB_bear_low(0),
double OB_bear_avg(0),
// latest range, for drawings, hold these variables, use these variables for strategy
double latest_bull_high(0),  // Variable to keep latest Bull OB high
double latest_bull_avg(0),  // Variable to keep latest Bull OB average
double latest_bull_low(0),  // Variable to keep latest Bull OB low
double latest_bear_high(0),  // Variable to keep latest Bear OB high
double latest_bear_avg(0),  // Variable to keep latest Bear OB average
double latest_bear_low(0);  // Variable to keep latest Bear OB low

// 20241230 added by Gary Armani
emaValForEntry = XAverage( close, EMA_Length );
ATRCalc = AvgTrueRange( ATR_Length ) * ATR_Multiplier;
if Dayofweek(Date[1]) <> 1 and  Dayofweek(Date) = 1 then Begin
	exitOnFridayCloseFlag = False; 
end;


TT = TotalTrades;
cc = Currentcontracts;
mp = marketposition;

// 20240219 entry at retracement
if mp <> mp[1] or tt <> tt[1] then 
Begin
	longSignalstatus1 = false;
	longSignalPrice1 = 0;
	shortSignalstatus1 = false;
	shortSignalPrice1 =0;
end;

//

isSessionOut = TradeStartTime <> TradeExitTime and time > TradeExitTime;


if BarType >= 2 and BarType < 5 then { Daily, Weekly, or Monthly bars }
	AnyVol = Volume 
else 
	AnyVol = Ticks;
	
// grosc = "------------- Volume Oscillator ---------"
 cumVol += AnyVol;
 
 //if barstate.islast and cumVol == 0
    //runtime.error("No volume is provided by the data vendor.")
 


shortVal = ema(AnyVol, shortlen);
longVal = ema(AnyVol, longlen);
osc = 100 * (shortVal - longVal) / longVal;

if useVO = true then Begin
	isVOBull = osc >= 0;
end
else Begin
	isVOBull = true;
end;

if useVO = true then Begin
	isVOBear = osc < 0;
end
else Begin
	isVOBear = true;
end;



// ignore grbb = "------------- Bollinger Bands Breakout Oscillator  ---------", do not support
//Style // ignore, maybe no need to implement
//bull_css = input(#089981, 'Bullish Color', group = grbb)
//bear_css = input(#f23645, 'Bearish Color' , group = grbb)

//------------------------------------------------------------------------------
//Calculation
//------------------------------------------------------------------------------
// 20241010
Avg = AverageFC( close, BB_Length );
SDev = StandardDev( close, BB_Length, 1 );
UpperBand = Avg + NumDevsUp * SDev;
LowerBand = Avg + NumDevsDn * SDev;
// 20241010 end						   
stdev = StandardDev( src, length, 1 ) *  mult;  //  ta.stdev(src, length) * mult
emaVal   = ema(src, length); // 

upperVal = emaVal + stdev;
lowerVal = emaVal - stdev;


bull = 0.0;
bear = 0.0;
bull_den = 0.0;
bear_den = 0.0;

for iCnt = 0 to length-1 Begin
	bull += Maxlist(src[iCnt] - upperVal[iCnt], 0);
    bear += Maxlist(lowerVal[iCnt] - src[iCnt], 0);
    
    bull_den += Absvalue(src[iCnt] - upperVal[iCnt]);
    bear_den += Absvalue(lowerVal[iCnt] - src[iCnt]);
end;
    
bull = bull/bull_den*100;
bear = bear/bear_den*100;

//------------------------------------------------------------------------------
//Plots
//------------------------------------------------------------------------------
//bull_grad = color.from_gradient(bull, 0, 100 , color.new(bull_css, 100), color.new(bull_css, 50))
//bear_grad = color.from_gradient(bear, 0, 100 , color.new(bear_css, 100), color.new(bear_css, 50))

if useBB = true then Begin
	isBullBB = bull > varbb;
end
else Begin
	isBullBB = true;
end;

if useBB = true then Begin
	isBearBB = bear > varbb;
end
else Begin
	isBearBB = true;
end;

//-----------------------------------------------------------

ob_period = periods + 1;  // Identify location of relevant Order Block candle
absmove = Absvalue(close[ob_period] - close[1]) / close[ob_period] * 100;  // Calculate absolute percent move from potential OB to last candle of subsequent candles
relmove = absmove >= threshold;  // Identify "Relevant move" by comparing the absolute move to the threshold

if colors = "DARK" then Begin
	bullcolor = White;
	bearcolor = Blue;
End
else Begin
	bullcolor = green;
	bearcolor = red;
end;

// Bullish Order Block Identification
bullishOB = close[ob_period] < open[ob_period];  // Determine potential Bullish OB candle (red candle)

upcandles = 0;
for iCnt = 1 to periods Begin
	upcandles += iff(close[iCnt] > open[iCnt] , 1 , 0) ; // Determine color of subsequent candles (must all be green to identify a valid Bearish OB)
    //upcandles
end;
    
OB_bull = bullishOB and upcandles = periods and relmove;  // Identification logic (red OB candle & subsequent green candles)
// becareful na value ??? use 0 instead
//OB_bull_high = OB_bull ? usewicks ? high[ob_period] : open[ob_period] : na  // Determine OB upper limit (Open or High depending on input)
OB_bull_high = IFF(OB_bull = True,iff(usewicks = True,high[ob_period],open[ob_period]),0);
//OB_bull_low = OB_bull ? low[ob_period] : na  // Determine OB lower limit (Low)
OB_bull_low = iff(OB_bull = True , low[ob_period] , 0);  // Determine OB lower limit (Low)
//OB_bull_avg = (OB_bull_high + OB_bull_low) / 2  // Determine OB middle line
OB_bull_avg = (OB_bull_high + OB_bull_low) / 2;    //

// Bearish Order Block Identification
bearishOB = close[ob_period] > open[ob_period] ; // Determine potential Bearish OB candle (green candle)
downcandles = 0;
for iCnt = 1 to periods Begin
	downcandles += iff(close[iCnt] < open[iCnt] , 1 , 0) ; // Determine color of subsequent candles (must all be red to identify a valid Bearish OB) 
end;
OB_bear = bearishOB and downcandles = periods and relmove;  // Identification logic (green OB candle & subsequent green candles)
OB_bear_high = iff(OB_bear = True , high[ob_period] , 0); // Determine OB upper limit (High)
OB_bear_low = iff(OB_bear = True , iff(usewicks , low[ob_period] , open[ob_period]) , 0);  // Determine OB lower limit (Open or Low depending on input)
OB_bear_avg = (OB_bear_low + OB_bear_high) / 2;  // Determine OB middle line


//****** insert code below, for drawings, not for info panel as in tradingview  -------- start 

if OB_bull_high > 0 then
    latest_bull_high = OB_bull_high;
    

if OB_bull_avg > 0 then
    latest_bull_avg = OB_bull_avg;
   

if OB_bull_low > 0 then
    latest_bull_low = OB_bull_low;
   

if OB_bear_high > 0 then
    latest_bear_high = OB_bear_high;
   

if OB_bear_avg > 0 then
    latest_bear_avg = OB_bear_avg;
   

if OB_bear_low > 0 then
    latest_bear_low = OB_bear_low;
   


/// end *******************


// it is hard to implement table information, ignore: Show Label for documentation tooltip? show latest info panel 
// ploting
//use dot instead. TS does not support triangle // plotshape(OB_bull, title='Bullish OB', style=shape.triangleup, color=bullcolor, textcolor=bullcolor, size=size.tiny, location=location.belowbar, offset=-ob_period, text='Bullish OB')  // Bullish OB Indicator
// tradingview draw line and extend to right. I only draw current line, implement this later if need it.
if OB_bull = True and Barstatus(1) = 2 then Begin
	// 20241010
	shortStopRangePct50 = 0;
	if enable_modify_stop_loss_candle = true then Begin
		// OB_bull_low = iff(OB_bull = True , low[ob_period] , 0);  // Determine OB lower limit (Low)
		if  close[ob_period] < Avg[ob_period] and close[1] > UpperBand[1] 
		 then Begin
			modify_stop_loss_candle_flag = true;
			longStopRangeMax = close[1];
			longStopRangemin = 	low[ob_period];
			longStopRangePct50 = low[ob_period] + (close[1]- low[ob_period])/2; 
																   
		end
		else Begin
			modify_stop_loss_candle_flag = false;
								
																	
		end;
	end
	else Begin
		modify_stop_loss_candle_flag = true;
	end;
	// and modify_stop_loss_candle_flag = true 
	// 20241010 end
	if	isVOBull and isBullBB  and isBull then Begin
		//plot5[ob_period](Low[ob_period] ,"Bullish OB",bullcolor);//, color=color.green
		//alert("New Bullish OB detected - This is NOT a BUY signal!");
		// 20241010 
		if  modify_stop_loss_candle_flag = true then Begin
			longstopPrice = longStopRangePct50;
		end;
		// 20241010 end																					   
		if exitOnFridayCloseFlag = false and  (Enable_EMA = false or ( Enable_EMA = true and close > emaValForEntry )) 
		and  mp = 0 and TradeStartTime = TradeExitTime 
		or TradeStartTime <> TradeExitTime and time > TradeStartTime and time < TradeExitTime then 
		Begin
			if Place_at_Retracement = false then begin  // long at market price
				if useMarketOrder = true then Begin
					Buy (  "LE" ) NumberofShares contracts  next bar at market;
				End
				else Begin
					Buy (  "LE2" ) NumberofShares contracts  next bar at high Stop;
				end;
				
				Entry_Price = Close;
				StopLoss_Price = OB_bull_low;
				StopLoss_Price2 = 0;
				if  modify_stop_loss_candle_flag = true then Begin
					StopLoss_Price2 = longstopPrice;  // = longStopRangePct50;
				end;
				Target_Price = Entry_Price +   (Entry_Price - StopLoss_Price)*rr;
			
			End
			else Begin              // long at retracement
				longSignalstatus1 = true;
				longSignalPrice1 = high - (high - OB_bull_low ) * Place_at_x_percent/100; 
				StopLoss_Price = OB_bull_low;
				Target_Price = longSignalPrice1 +   (longSignalPrice1 - StopLoss_Price)*rr;
			end;
			
			
			
		end;
	end; 
	
	//value1 = Text_new(date[ob_period],time[ob_period],Low[ob_period]- AvgTrueRange(20)/4,"Bullish OB");
	//Text_setcolor(value1,bullcolor);	 
end;


if Place_at_Retracement = true then Begin
	if longSignalstatus1 = true and longSignalPrice1 > 0 then Begin
		Buy (  "LE_limit" ) NumberofShares contracts  next bar at longSignalPrice1 limit;
	end;
		
end;

if mp = 1 then Begin
	// comment lines below becauese of use atr stop 
	//sell (  "L_s" ) NumberofShares contracts  next bar at StopLoss_Price stop;
	if EnableRR  = true then 
	Begin
		sell (  "L_p" ) NumberofShares contracts  next bar at Target_Price limit;
	end;
	
	//if StopLoss_Price2 > 0 and close < StopLoss_Price2 then Begin
		//sell (  "L_s2" ) NumberofShares contracts  next bar at Market;
	//end;
end;

if  showbull then Begin  //OB_bull and	
	if longStopRangePct50 > 0 then Begin
		//plot15(longStopRangePct50,"Bullish OB STOP"); //bullcolor
		if close[2] < longStopRangePct50 then Begin
			longStopRangePct50 = 0;
		end;
	end;
end;

if OB_bear = True  and Barstatus(1) = 2 then Begin
	
	// 20241010 
	longStopRangePct50 = 0;
	if enable_modify_stop_loss_candle = true then Begin
		
		if  close[ob_period] > Avg[ob_period] and close[1] < LowerBand[1] 
																  
		 then Begin
			modify_stop_loss_candle_flag = true;
			shortStopRangeMax = high[ob_period];
			shortStopRangemin = close[1] ;
			shortStopRangePct50 = high[ob_period] - (high[ob_period] - close[1] )/2;	
		end
		else Begin
			modify_stop_loss_candle_flag = False;				  
		end;
	end
	else Begin
		modify_stop_loss_candle_flag = true;
	end;
	// 20241010 end					
	if isVOBear and isBearBB and isBear then Begin												
		//plot9[ob_period](high[ob_period] ,"Bearish OB",bearcolor);//, color=color.green
		//alert("New Bearish OB detected - This is NOT a SELL signal!");
		if  modify_stop_loss_candle_flag = true then Begin
			shortstopPrice = shortStopRangePct50;
		end;
		if exitOnFridayCloseFlag = false and  (Enable_EMA = false or ( Enable_EMA = true and close < emaValForEntry )) 
		and  mp = 0 and TradeStartTime = TradeExitTime 
		or TradeStartTime <> TradeExitTime and time > TradeStartTime and time < TradeExitTime then 
		Begin
			if Place_at_Retracement = false then begin  // short at market price
				if useMarketOrder = true then Begin
					sellshort (  "SE" ) NumberofShares contracts  next bar at market;
				End
				else Begin
					sellshort (  "SE2" ) NumberofShares contracts  next bar at low limit;
				end;
				
				Entry_Price = close;
				StopLoss_Price = OB_bear_high;
				if  modify_stop_loss_candle_flag = true then Begin
					StopLoss_Price2 = shortstopPrice;  // = shortStopRangePct50;
				end;
				Target_Price = Entry_Price -   ( StopLoss_Price - Entry_Price )*rr;
			
			End
			else Begin   // short at retracement
				shortSignalstatus1 = true;
				shortSignalPrice1 = low + (OB_bear_high - low  ) * Place_at_x_percent/100; 
				StopLoss_Price = OB_bear_high;
				Target_Price = shortSignalPrice1 -   (StopLoss_Price -shortSignalPrice1  )*rr;
			end;
			
			
			
		end;
	end;
	
	//value1 = Text_new(date[ob_period],time[ob_period],High[ob_period] + AvgTrueRange(20)/4,"Bearish OB");
	//Text_setcolor(value1,bearcolor);	 
end;


if Place_at_Retracement = true then Begin
	if shortSignalstatus1 = true and shortSignalPrice1 > 0 then Begin
		sellshort (  "SE_limit" ) NumberofShares contracts  next bar at shortSignalPrice1 limit;
	end;		
end;


if mp = -1 then Begin
	
	// comment lines below becauese of use atr stop 
	//Buytocover (  "S_s" ) NumberofShares contracts  next bar at StopLoss_Price stop;
	
	if EnableRR  = true then 
	Begin
		Buytocover (  "S_p" ) NumberofShares contracts  next bar at Target_Price limit;
	end;
	
	//if StopLoss_Price2 > 0 and close > StopLoss_Price2 then Begin
		//Buytocover (  "S_s2" ) NumberofShares contracts  next bar at market;
	//end;
end;

	
if  showbear then Begin  //OB_bear and
	
	if shortStopRangePct50 > 0 then Begin
		if close[2] >  shortStopRangePct50 then Begin
			shortStopRangePct50 = 0;
		end;	
	end;				   
end;
// Plotting
{
plotshape(OB_bear, title='Bearish OB', style=shape.triangledown, color=bearcolor, textcolor=bearcolor, size=size.tiny, location=location.abovebar, offset=-ob_period, text='Bearish OB')  // Bearish OB Indicator
bear1 = plot(OB_bear_low, title='Bearish OB Low', style=plot.style_linebr, color=bearcolor, offset=-ob_period, linewidth=3)  // Bearish OB Lower Limit
bear2 = plot(OB_bear_high, title='Bearish OB High', style=plot.style_linebr, color=bearcolor, offset=-ob_period, linewidth=3)  // Bearish OB Upper Limit
fill(bear1, bear2, color=bearcolor, title='Bearish OB fill', transp=0)  // Fill Bearish OB
plotshape(OB_bear_avg, title='Bearish OB Average', style=shape.cross, color=bearcolor, size=size.normal, location=location.absolute, offset=-ob_period)  // Bullish OB Average
}

// didn't implemt plot entry/limit price. hard to implent in TS
{
slplot = plot(strategy.position_size != 0 and useONe? StopLoss_Price : na,"Stop Loss",style = plot.style_circles,color=color.red)
limtplot = plot(strategy.position_size != 0  and useONe? Target_Price : na,"Limit",style = plot.style_circles,color=color.green)
entryplot = plot(strategy.position_size != 0  and useONe? Entry_Price : na,"Entry",style = plot.style_circles,color=color.black)

fill(entryplot,slplot,color = color.rgb(255, 82, 82, 90))
fill(limtplot,entryplot,color = color.rgb(82, 255, 91, 90))
}

// Ignore  info panel


// close position after sessin. 
if isSessionOut = True then Begin
	sell ("L_c") next bar at market;
	Buytocover ("S_c") next bar at market;

end;

// change ATRCalc to fixed price, so it will not change.
// 20250203

if Enable_ATR_stop = true then Begin

	// for long
	if MP = 1 then 
	begin
		if TT <> TT[1] or MP[1] <> 1 or High > PosHigh then 
			PosHigh = High;
		// atr should be fixed.
		if MP[1] <> 1 then Begin
			ATRCalcFix = ATRCalc;
		end;
		
		Sell ( !( "AtrLX" ) ) next bar at PosHigh - ATRCalcFix stop;
	end
	else
		Sell ( !( "AtrLX-eb" ) ) next bar at High - ATRCalc stop;


	/// for short
	if MP = -1 then 
	begin
		if TT <> TT[1] or MP[1] <> -1 or Low < PosLow then 
			PosLow = Low;
		if MP[1] <> -1 then Begin
			ATRCalcFix = ATRCalc;
		end;
		Buy To Cover ( !( "AtrSX" ) ) next bar at PosLow + ATRCalcFix stop;
	end
	else
		Buy To Cover ( !( "AtrSX-eb" ) ) next bar at Low + ATRCalc stop;	
	

end;





if ClosePosition_Friday = true then Begin
	if Dayofweek(date) = 5 then Begin
		if time >= Friday_ClosePositionTime and time[1] <= Friday_ClosePositionTime then Begin
			if mp = 1 then Begin
				sell ("L_mx") next bar at Market;
				exitOnFridayCloseFlag = true;
			End
			else if mp = -1 then Begin
				buytocover ("S_mx") next bar at market; 
				exitOnFridayCloseFlag = true;
			end;
		end;
	end;

end;

// added stoploss by Gary Armani 20250220
if Enable_maximum_stop_loss = true then 
Begin
	if PositionBasis then
		SetStopPosition
	else
		SetStopShare ;
	
	SetStopLoss( Amount ) ;
end;


{
代码复杂，做一些记录
指标的原理是：
OB_bull定义obder block， 出现一个阴K，然后出现连续多个阳K，那么认为是一个ob_bull. 反之OB_bear也成立。
且有isbull(是否做多), isVOBull(震荡过滤器过滤), isBullBB(布林带过滤).
指标上，如果只是显示bullish ob, 那么代表这个模式找到了，如果同时显示了白色圆点，才表示满足了各种过滤器后的信号。
我修改了TradingView指标，显示了历史的ob模式的数据, high,low,avg line.方便校验策略

}