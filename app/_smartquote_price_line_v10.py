# VERBATIM original SmartQuote V10 deterministic price_line function.
# Source: PulsefitnessIT/Pulse_SmartQuote, feature/contracts-os-accepted-handoff
# Source engine.py Git blob: b40a845ec9abc751ceff16574208fb7995168a8e
# Local clone preserves the exact function body, with POLICY injected per-call
# using a private Python function namespace, without mutating module globals.
# No data files, customers, prices or secrets are bundled here.
"""Original SmartQuote V10 arithmetic, isolated for thread-safe source parity.

Only the trusted original function is executed; caller-supplied JSON is data.
No customer PDF issuance or commercial approval results from this calculation.
"""
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from types import FunctionType


def money(x):
    return float(Decimal(str(x)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))


def price_line(asset,level,tier,discount):
 if asset.get('excluded'):return None
 qty=max(1,int(asset.get('qty',1)))
 manual=asset.get('manual_annual_unit')
 if manual is not None and manual != '':
  try:
   unit=Decimal(str(manual))
   if unit<=0 or unit>Decimal('1000000'):return None
   discounted=unit*(Decimal('1')-Decimal(str(discount))/Decimal('100'))
   shown_unit=money(discounted)
   net=Decimal(str(shown_unit))*qty
   return {'unit':shown_unit,'annual':money(net),'minimum':money(0),'base_unit':money(unit),'rrp':None,'qty':qty,'rate':None,'manual':True,'basis':'manual','rule':'Evidence-backed annual unit rate before quotation discount'}
  except (ValueError,ArithmeticError):return None
 s=asset.get('selected')
 if not s and asset.get('historic_rrp') and asset.get('historic_rate_percent'):
  # Historical evidence can populate a comparison estimate, but is not a
  # verified current RRP and cannot make a customer quotation issue-ready.
  try:
   old=Decimal(str(asset['historic_rrp']))
   historic_rate=Decimal(str(asset['historic_rate_percent']))/Decimal('100')
   special=Decimal(str(asset.get('historic_annual_unit') or 0))-old*historic_rate
   raw=(old*historic_rate+special)*Decimal(str(PRICING['tiers'][tier]))
   unit=money(raw*(Decimal('1')-Decimal(str(discount))/Decimal('100')))
   return {'unit':unit,'annual':money(Decimal(str(unit))*qty),'minimum':0,'base_unit':money(raw),
           'rrp':money(old),'qty':qty,'rate':float(historic_rate),'basis':'historic-reference',
           'rule':'Historic RRP ONLY — update to current RRP before customer issue',
           'historic_special_annual':money(special)}
  except (ValueError,ArithmeticError):return None
 if not s or s.get('eligible')=='No' or not isinstance(s.get('rrp'),(int,float)) or s['rrp']<=0:return None
 rate=RATES.get(s.get('rate_group') or '')
 if not rate:return None
 base=float(s['rrp'])*float(rate.get(level.lower(),rate['standard']))
 console=CONSOLES.get(s.get('console',''),{'multiplier':1,'uplift':0}); console={**console, 'multiplier':float(s.get('console_pricing',console['multiplier']))}
 annualunit=(base*float(console['multiplier'])+float(console['uplift'])+rate['uplift'])*PRICING['tiers'][tier]
 unit=money(annualunit*(1-discount/100))
 line=unit*qty
 minimum=(float(s['rrp'])*rate['minimum']*float(console['multiplier'])+float(console['uplift'])+rate['uplift'])*PRICING['tiers'][tier]*qty
 return {'unit':unit,'annual':money(line),'minimum':money(minimum),'base_unit':money(base),'rrp':money(s['rrp']),'qty':qty,'rate':rate.get(level.lower(),rate['standard']),'basis':s.get('price_origin','mapped'),'rule':s.get('pricing_rule','Source tariff')}


def original_v10_price_line(asset, level, tier, discount, pricing):
    """Run the original V10 source function with isolated source-derived globals.

    No shared PRICING/RATES/CONSOLES globals are modified. A concurrent source
    revision cannot alter another request's arithmetic midway through a quote.
    """
    if not isinstance(pricing, dict) or not isinstance(pricing.get('tiers'), dict):
        raise ValueError('Original V10 price policy is missing.')
    rates=pricing.get('rates')
    console_rules=pricing.get('console_rules')
    if not isinstance(rates,list) or not isinstance(console_rules,list):
        raise ValueError('Original V10 source rate or console rules are missing.')
    rate_map={str(r['group']):r for r in rates if isinstance(r,dict) and r.get('group')}
    console_map={str(r['name']):r for r in console_rules if isinstance(r,dict) and r.get('name')}
    sandbox=dict(price_line.__globals__)
    sandbox.update({'PRICING':pricing,'RATES':rate_map,'CONSOLES':console_map})
    private=FunctionType(price_line.__code__,sandbox,price_line.__name__,
                         price_line.__defaults__,price_line.__closure__)
    return private(asset,level,tier,discount)
