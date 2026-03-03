import json
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
# CONFIGURATION
# ============================================================

ANNUAL_RATE    = 0.60
MONTHLY_RATE   = ANNUAL_RATE / 12   # 0.05
N_MONTHS       = 12
MIN_LOAN       = 10_000
MAX_LOAN       = 50_000
DSCR_BUFFER    = 1.5

def fmt_money(v):
    """Simple £ formatter for reason strings."""
    return f'£{v:,.0f}'

# ============================================================
# LENDER REGISTRY — 221 entries, bank-statement keyword matching
# ============================================================

LENDER_REGISTRY = [
    # ── UNSECURED / REVOLVING / FINTECH ──
    {'name': 'iwoca',                       'category': 'Unsecured Lending',   'product': 'Revolving Credit',          'keywords': ['iwoca']},
    {'name': 'Capital on Tap',              'category': 'Unsecured Lending',   'product': 'Revolving Credit',          'keywords': ['capital on tap']},
    {'name': 'Funding Circle',              'category': 'Unsecured Lending',   'product': 'Term Loan',                 'keywords': ['funding circle']},
    {'name': 'YouLend',                     'category': 'Unsecured Lending',   'product': 'Revenue-Based',             'keywords': ['youlend']},
    {'name': 'Liberis',                     'category': 'Unsecured Lending',   'product': 'Merchant Cash Advance',     'keywords': ['liberis']},
    {'name': '365 Business Finance',        'category': 'Unsecured Lending',   'product': 'Merchant Cash Advance',     'keywords': ['365 business', '365 finance', '365 bf', '365bf']},
    {'name': 'Capify',                      'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['capify']},
    {'name': 'Nucleus Commercial Finance',  'category': 'Unsecured Lending',   'product': 'Term Loan',                 'keywords': ['nucleus commercial', 'nucleus finance']},
    {'name': 'Fleximize',                   'category': 'Unsecured Lending',   'product': 'Flexible Loan',             'keywords': ['fleximize']},
    {'name': 'Bizcap',                      'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['bizcap']},
    {'name': 'MarketFinance',               'category': 'Unsecured Lending',   'product': 'Invoice Finance / Loan',    'keywords': ['marketfinance', 'market finance']},
    {'name': 'Kriya',                       'category': 'Unsecured Lending',   'product': 'B2B Payments / Credit',     'keywords': ['kriya']},
    {'name': 'Boost Capital',               'category': 'Unsecured Lending',   'product': 'Merchant Cash Advance',     'keywords': ['boost capital']},
    {'name': 'Merchant Money',              'category': 'Unsecured Lending',   'product': 'Merchant Cash Advance',     'keywords': ['merchant money']},
    {'name': 'Sedge',                       'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['sedge']},
    {'name': 'Mumford Lending',             'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['mumford']},
    {'name': 'Cubefunder',                  'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['cubefunder']},
    {'name': 'Ezbob',                       'category': 'Unsecured Lending',   'product': 'Term Loan',                 'keywords': ['ezbob']},
    {'name': 'Spotcap',                     'category': 'Unsecured Lending',   'product': 'Credit Line',               'keywords': ['spotcap']},
    {'name': 'Clearco',                     'category': 'Unsecured Lending',   'product': 'Revenue-Based',             'keywords': ['clearco']},
    {'name': 'Uncapped',                    'category': 'Unsecured Lending',   'product': 'Revenue-Based',             'keywords': ['uncapped']},
    {'name': 'Playter',                     'category': 'Unsecured Lending',   'product': 'B2B BNPL',                  'keywords': ['playter']},
    {'name': 'Swoop',                       'category': 'Unsecured Lending',   'product': 'Marketplace',               'keywords': ['swoop']},
    {'name': 'Wayflyer',                    'category': 'Unsecured Lending',   'product': 'Revenue-Based',             'keywords': ['wayflyer']},
    {'name': 'ThinCats',                    'category': 'Unsecured Lending',   'product': 'Term Loan',                 'keywords': ['thincats', 'thin cats']},
    {'name': 'Assetz Capital',              'category': 'Unsecured Lending',   'product': 'P2P Lending',               'keywords': ['assetz capital', 'assetz']},
    {'name': 'Folk2Folk',                   'category': 'Unsecured Lending',   'product': 'P2P Lending',               'keywords': ['folk2folk']},
    {'name': 'Lendable',                    'category': 'Unsecured Lending',   'product': 'Consumer/SME',              'keywords': ['lendable']},
    {'name': 'Zopa Business',               'category': 'Unsecured Lending',   'product': 'Term Loan',                 'keywords': ['zopa']},
    {'name': 'Esme Loans',                  'category': 'Unsecured Lending',   'product': 'Term Loan',                 'keywords': ['esme loans', 'esme']},
    {'name': 'Tide',                        'category': 'Unsecured Lending',   'product': 'Overdraft / Credit',        'keywords': ['tide']},
    {'name': 'Moneyway',                    'category': 'Unsecured Lending',   'product': 'HP / Loan',                 'keywords': ['moneyway']},
    {'name': 'Reward Finance Group',        'category': 'Unsecured Lending',   'product': 'Cashflow Loan',             'keywords': ['reward finance', 'reward funding']},
    {'name': 'Just Cashflow',               'category': 'Unsecured Lending',   'product': 'Revolving Credit',          'keywords': ['just cashflow', 'justcashflow']},
    {'name': 'Catalyst Finance',            'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['catalyst finance']},
    {'name': 'FundingXchange',              'category': 'Unsecured Lending',   'product': 'Marketplace',               'keywords': ['fundingxchange']},
    {'name': 'Caple',                       'category': 'Unsecured Lending',   'product': 'Growth Finance',            'keywords': ['caple']},
    {'name': 'Love Finance',                'category': 'Unsecured Lending',   'product': 'Business Loans',            'keywords': ['love finance', 'lovefinance']},
    {'name': 'Growth Lending',              'category': 'Unsecured Lending',   'product': 'Venture Debt',              'keywords': ['growth lending']},
    {'name': 'Lending Crowd',               'category': 'Unsecured Lending',   'product': 'P2P Lending',               'keywords': ['lending crowd']},
    {'name': 'Funding Knight',              'category': 'Unsecured Lending',   'product': 'P2P Lending',               'keywords': ['funding knight']},
    {'name': 'ArchOver',                    'category': 'Unsecured Lending',   'product': 'P2P Lending',               'keywords': ['archover']},
    {'name': 'Adelpha Capital',             'category': 'Unsecured Lending',   'product': 'Secured / Unsecured',       'keywords': ['adelpha']},
    {'name': 'Adsum',                       'category': 'Unsecured Lending',   'product': 'Tax Funding',               'keywords': ['adsum']},
    {'name': 'Business Enterprise Fund',    'category': 'Unsecured Lending',   'product': 'Community Lending',         'keywords': ['business enterprise fund']},
    {'name': 'Cashera',                     'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['cashera']},
    {'name': 'Credit4',                     'category': 'Unsecured Lending',   'product': 'Revolving Facility',        'keywords': ['credit4', 'credit 4']},
    {'name': 'Crowd2Fund',                  'category': 'Unsecured Lending',   'product': 'P2P Lending',               'keywords': ['crowd2fund']},
    {'name': 'Elect Capital',               'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['elect capital']},
    {'name': 'Finance For Enterprise',      'category': 'Unsecured Lending',   'product': 'Community Lending',         'keywords': ['finance for enterprise']},
    {'name': 'GOT Capital',                 'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['got capital']},
    {'name': 'Juice',                       'category': 'Unsecured Lending',   'product': 'Unsecured Loan',            'keywords': ['juice']},
    {'name': 'Kingsway',                    'category': 'Unsecured Lending',   'product': 'Term Loan',                 'keywords': ['kingsway']},
    {'name': 'MaxCap',                      'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['maxcap']},
    {'name': 'Monmouth Business Loan',      'category': 'Unsecured Lending',   'product': 'Term Loan',                 'keywords': ['monmouth']},
    {'name': 'Momenta',                     'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['momenta']},
    {'name': 'MyCashline',                  'category': 'Unsecured Lending',   'product': 'Revolving Credit',          'keywords': ['mycashline', 'my cashline']},
    {'name': 'Rocking Horse',               'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['rocking horse']},
    {'name': 'Sprk Capital',                'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['sprk capital', 'sprk']},
    {'name': 'Swiftfund',                   'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['swiftfund', 'swift fund']},
    {'name': 'Swishfund',                   'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['swishfund', 'swish fund']},
    # ── ASSET FINANCE / LEASING ──
    {'name': 'Close Brothers',              'category': 'Asset Finance',       'product': 'Asset Finance / Leasing',   'keywords': ['close brothers']},
    {'name': 'Lombard',                     'category': 'Asset Finance',       'product': 'Asset Finance / Leasing',   'keywords': ['lombard']},
    {'name': 'Aldermore',                   'category': 'Asset Finance',       'product': 'Asset Finance / Leasing',   'keywords': ['aldermore']},
    {'name': 'Shawbrook',                  'category': 'Asset Finance',       'product': 'Asset Finance / Leasing',   'keywords': ['shawbrook']},
    {'name': 'United Trust Bank',           'category': 'Asset Finance',       'product': 'Asset Finance / Leasing',   'keywords': ['united trust']},
    {'name': 'Paragon Bank',                'category': 'Asset Finance',       'product': 'Asset Finance / Leasing',   'keywords': ['paragon']},
    {'name': 'Haydock Finance',             'category': 'Asset Finance',       'product': 'Asset Finance / Leasing',   'keywords': ['haydock']},
    {'name': 'Time Finance',                'category': 'Asset Finance',       'product': 'Asset Finance / Leasing',   'keywords': ['time finance']},
    {'name': 'Grenke',                      'category': 'Asset Finance',       'product': 'Leasing',                   'keywords': ['grenke']},
    {'name': 'Shire Leasing',               'category': 'Asset Finance',       'product': 'Leasing',                   'keywords': ['shire leasing']},
    {'name': 'Wesleyan Bank',               'category': 'Asset Finance',       'product': 'Professional Finance',      'keywords': ['wesleyan']},
    {'name': 'Hampshire Trust Bank',        'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['hampshire trust']},
    {'name': 'Stellantis Financial Services','category': 'Asset Finance',      'product': 'Vehicle Finance',           'keywords': ['stellantis']},
    {'name': 'Armada Asset Finance',        'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['armada']},
    {'name': 'SME Finance Partners',        'category': 'Asset Finance',       'product': 'Business Finance',          'keywords': ['sme finance']},
    {'name': 'Premium Credit',              'category': 'Asset Finance',       'product': 'Insurance Premium Finance', 'keywords': ['premium credit']},
    {'name': 'Simply Asset Finance',        'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['simply asset', 'simply finance']},
    {'name': 'Hitachi Capital',             'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['hitachi capital', 'hitachi']},
    {'name': 'Novuna Business Finance',     'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['novuna']},
    {'name': 'First Asset Finance',         'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['first asset finance']},
    {'name': 'Bibby Leasing',               'category': 'Asset Finance',       'product': 'Leasing',                   'keywords': ['bibby leasing']},
    {'name': 'Investec Asset Finance',      'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['investec']},
    {'name': 'Societe Generale Equipment Finance','category': 'Asset Finance', 'product': 'Equipment Finance',         'keywords': ['societe generale', 'sgef']},
    {'name': 'DLL Group',                   'category': 'Asset Finance',       'product': 'Leasing',                   'keywords': ['dll', 'de lage landen']},
    {'name': 'BNP Paribas Leasing',         'category': 'Asset Finance',       'product': 'Leasing',                   'keywords': ['bnp paribas leasing', 'bnp leasing']},
    {'name': 'Siemens Financial Services',  'category': 'Asset Finance',       'product': 'Equipment Finance',         'keywords': ['siemens financial']},
    {'name': 'JCB Finance',                 'category': 'Asset Finance',       'product': 'Equipment Finance',         'keywords': ['jcb finance']},
    {'name': 'Toyota Financial Services',   'category': 'Asset Finance',       'product': 'Vehicle Finance',           'keywords': ['toyota financial']},
    {'name': 'Mercedes-Benz Financial',     'category': 'Asset Finance',       'product': 'Vehicle Finance',           'keywords': ['mercedes financial', 'mercedes-benz financial']},
    {'name': 'BMW Financial Services',      'category': 'Asset Finance',       'product': 'Vehicle Finance',           'keywords': ['bmw financial']},
    {'name': 'Volkswagen Financial Services','category': 'Asset Finance',      'product': 'Vehicle Finance',           'keywords': ['volkswagen financial', 'vw financial']},
    {'name': 'Ford Motor Credit',           'category': 'Asset Finance',       'product': 'Vehicle Finance',           'keywords': ['ford credit', 'ford motor credit']},
    {'name': 'Black Horse',                 'category': 'Asset Finance',       'product': 'Vehicle Finance',           'keywords': ['black horse']},
    {'name': 'Lex Autolease',               'category': 'Asset Finance',       'product': 'Vehicle Leasing',           'keywords': ['lex autolease']},
    {'name': 'Alphabet (BMW)',              'category': 'Asset Finance',       'product': 'Fleet Leasing',             'keywords': ['alphabet']},
    {'name': 'ALD Automotive',              'category': 'Asset Finance',       'product': 'Fleet Leasing',             'keywords': ['ald automotive']},
    {'name': 'Ayvens',                      'category': 'Asset Finance',       'product': 'Fleet Leasing',             'keywords': ['ayvens']},
    {'name': 'LeasePlan',                   'category': 'Asset Finance',       'product': 'Fleet Leasing',             'keywords': ['leaseplan']},
    {'name': 'Praetura Asset Finance',      'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['praetura']},
    {'name': 'Johnson Reed',                'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['johnson reed']},
    {'name': 'White Oak UK',                'category': 'Asset Finance',       'product': 'Equipment Finance',         'keywords': ['white oak']},
    {'name': 'Asset Advantage',             'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['asset advantage']},
    {'name': 'Allica Bank',                 'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['allica']},
    # ── INVOICE FINANCE / FACTORING / ABL ──
    {'name': 'Bibby Financial Services',    'category': 'Invoice Finance',     'product': 'Factoring / Discounting',   'keywords': ['bibby financial', 'bibby']},
    {'name': 'Close Brothers IF',           'category': 'Invoice Finance',     'product': 'Invoice Discounting',       'keywords': ['close brothers']},
    {'name': 'IGF Invoice Finance',         'category': 'Invoice Finance',     'product': 'ABL',                       'keywords': ['igf']},
    {'name': 'Novuna Business Cash Flow',   'category': 'Invoice Finance',     'product': 'Factoring / Discounting',   'keywords': ['novuna']},
    {'name': 'Paragon Business Finance',    'category': 'Invoice Finance',     'product': 'Invoice Discounting',       'keywords': ['paragon']},
    {'name': 'ABN AMRO Commercial Finance', 'category': 'Invoice Finance',     'product': 'ABL',                       'keywords': ['abn amro']},
    {'name': 'Praetura Commercial Finance', 'category': 'Invoice Finance',     'product': 'ABL',                       'keywords': ['praetura']},
    {'name': 'Investec Capital Solutions',  'category': 'Invoice Finance',     'product': 'ABL',                       'keywords': ['investec capital']},
    {'name': 'Leumi ABL',                   'category': 'Invoice Finance',     'product': 'ABL',                       'keywords': ['leumi']},
    {'name': 'Secure Trust Bank',           'category': 'Invoice Finance',     'product': 'Invoice Discounting',       'keywords': ['secure trust']},
    {'name': 'Skipton Business Finance',    'category': 'Invoice Finance',     'product': 'Invoice Discounting',       'keywords': ['skipton']},
    {'name': 'Pulse Cashflow Finance',      'category': 'Invoice Finance',     'product': 'Factoring',                 'keywords': ['pulse cashflow']},
    {'name': 'Optimum Finance',             'category': 'Invoice Finance',     'product': 'Selective IF',              'keywords': ['optimum finance']},
    {'name': 'Satago',                      'category': 'Invoice Finance',     'product': 'Selective IF',              'keywords': ['satago']},
    {'name': 'Sonovate',                    'category': 'Invoice Finance',     'product': 'Back-Office Finance',       'keywords': ['sonovate']},
    {'name': 'Ultimate Finance',            'category': 'Invoice Finance',     'product': 'Factoring / Discounting',   'keywords': ['ultimate finance']},
    {'name': 'Team Factors',                'category': 'Invoice Finance',     'product': 'Factoring',                 'keywords': ['team factors']},
    {'name': 'Alex Lawrie Factors',         'category': 'Invoice Finance',     'product': 'Factoring',                 'keywords': ['alex lawrie']},
    {'name': 'Salford Trading Finance',     'category': 'Invoice Finance',     'product': 'Factoring',                 'keywords': ['salford trading']},
    {'name': 'Davenham',                    'category': 'Invoice Finance',     'product': 'ABL',                       'keywords': ['davenham']},
    {'name': 'FGI Finance',                 'category': 'Invoice Finance',     'product': 'ABL',                       'keywords': ['fgi finance']},
    {'name': 'GapCap',                      'category': 'Invoice Finance',     'product': 'Working Capital',           'keywords': ['gapcap']},
    {'name': 'eCapital',                    'category': 'Invoice Finance',     'product': 'Factoring / Discounting',   'keywords': ['ecapital', 'e-capital']},
    {'name': 'Trade Plus 24',               'category': 'Invoice Finance',     'product': 'Selective IF',              'keywords': ['trade plus 24', 'tradeplus24']},
    {'name': 'Triver',                      'category': 'Invoice Finance',     'product': 'Invoice Finance',           'keywords': ['triver']},
    # ── TRADE / SUPPLIER FINANCE ──
    {'name': 'Ebury',                       'category': 'Trade Finance',       'product': 'Supplier Finance / FX',     'keywords': ['ebury']},
    {'name': 'Lenkie',                      'category': 'Trade Finance',       'product': 'Supplier Finance RCF',      'keywords': ['lenkie']},
    {'name': 'Seneca',                      'category': 'Trade Finance',       'product': 'Supplier Finance',          'keywords': ['seneca']},
    {'name': 'Treyd',                       'category': 'Trade Finance',       'product': 'Purchase Order Finance',    'keywords': ['treyd']},
    {'name': 'WeDo Trade Finance',          'category': 'Trade Finance',       'product': 'Trade Finance',             'keywords': ['wedo trade', 'wedo']},
    # ── eCOMMERCE FINANCE ──
    {'name': 'Capchase',                    'category': 'eCommerce Finance',   'product': 'Revenue-Based',             'keywords': ['capchase']},
    {'name': 'Velocity Juice',              'category': 'eCommerce Finance',   'product': 'Revenue-Based',             'keywords': ['velocity juice']},
    # ── SECURED LENDING ──
    {'name': 'Bluecroft Finance',           'category': 'Secured Lending',     'product': 'Secured Business Loan',     'keywords': ['bluecroft']},
    {'name': 'MS Lending Group',            'category': 'Secured Lending',     'product': 'Secured Business Loan',     'keywords': ['ms lending']},
    {'name': 'Nationwide Finance',          'category': 'Secured Lending',     'product': 'Secured Business Loan',     'keywords': ['nationwide finance']},
    # ── CHALLENGER BANKS ──
    {'name': 'OakNorth Bank',               'category': 'Challenger Bank',     'product': 'Term Loan / Property',      'keywords': ['oaknorth']},
    {'name': 'Metro Bank',                  'category': 'Challenger Bank',     'product': 'Full Service',              'keywords': ['metro bank']},
    {'name': 'Starling Bank',               'category': 'Challenger Bank',     'product': 'Business Banking',          'keywords': ['starling']},
    {'name': 'Atom Bank',                   'category': 'Challenger Bank',     'product': 'Savings & Mortgages',       'keywords': ['atom bank']},
    {'name': 'Monzo Business',              'category': 'Challenger Bank',     'product': 'Business Banking',          'keywords': ['monzo']},
    {'name': 'Revolut Business',            'category': 'Challenger Bank',     'product': 'Business Banking',          'keywords': ['revolut']},
    {'name': 'Zempler Bank',                'category': 'Challenger Bank',     'product': 'Business Banking',          'keywords': ['zempler', 'cashplus']},
    {'name': 'Cambridge & Counties Bank',   'category': 'Challenger Bank',     'product': 'Property & Asset',          'keywords': ['cambridge & counties', 'cambridge and counties']},
    {'name': 'Cynergy Bank',                'category': 'Challenger Bank',     'product': 'Commercial Lending',        'keywords': ['cynergy']},
    {'name': 'Arbuthnot Latham',            'category': 'Challenger Bank',     'product': 'Private & Commercial',      'keywords': ['arbuthnot']},
    {'name': 'Triodos Bank',                'category': 'Challenger Bank',     'product': 'Ethical Banking',           'keywords': ['triodos']},
    {'name': 'Unity Trust Bank',            'category': 'Challenger Bank',     'product': 'Social Enterprise',         'keywords': ['unity trust']},
    {'name': 'Handelsbanken',               'category': 'Challenger Bank',     'product': 'Relationship Banking',      'keywords': ['handelsbanken']},
    {'name': 'Hodge Bank',                  'category': 'Challenger Bank',     'product': 'Specialist',                'keywords': ['hodge bank', 'hodge']},
    {'name': 'Recognise Bank',              'category': 'Challenger Bank',     'product': 'SME Lending',               'keywords': ['recognise']},
    {'name': 'PCF Bank',                    'category': 'Challenger Bank',     'product': 'Specialist',                'keywords': ['pcf bank']},
    # ── BRIDGING / PROPERTY ──
    {'name': 'Together Money',              'category': 'Bridging / Property', 'product': 'Bridging & Commercial',     'keywords': ['together money', 'together']},
    {'name': 'West One Loans',              'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['west one']},
    {'name': 'MT Finance',                  'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['mt finance']},
    {'name': 'LendInvest',                  'category': 'Bridging / Property', 'product': 'Bridging & BTL',            'keywords': ['lendinvest']},
    {'name': 'Octopus Real Estate',         'category': 'Bridging / Property', 'product': 'Bridging & Development',    'keywords': ['octopus real estate', 'octopus property']},
    {'name': 'Precise Mortgages',           'category': 'Bridging / Property', 'product': 'Bridging & BTL',            'keywords': ['precise mortgages', 'precise']},
    {'name': 'Maslow Capital',              'category': 'Bridging / Property', 'product': 'Bridging & Development',    'keywords': ['maslow capital', 'maslow']},
    {'name': 'Castle Trust Bank',           'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['castle trust']},
    {'name': 'Somo',                        'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['somo']},
    {'name': 'Tuscan Capital',              'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['tuscan capital']},
    {'name': 'TAB',                         'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['tab lending', 'tab property']},
    {'name': 'Greenfield Finance',          'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['greenfield']},
    {'name': 'Kuflink',                     'category': 'Bridging / Property', 'product': 'Bridging & P2P',            'keywords': ['kuflink']},
    {'name': 'Magnet Capital',              'category': 'Bridging / Property', 'product': 'Development',               'keywords': ['magnet capital']},
    {'name': 'Roma Finance',                'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['roma finance']},
    {'name': 'MFS',                         'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['market financial', 'mfs']},
    {'name': 'Fiduciam',                    'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['fiduciam']},
    {'name': 'Glenhawk',                    'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['glenhawk']},
    {'name': 'Ortus Secured Finance',       'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['ortus']},
    {'name': 'Spring Finance',              'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['spring finance']},
    {'name': 'Oblix Capital',               'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['oblix']},
    {'name': 'Interbridge',                 'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['interbridge']},
    {'name': 'Interbay Commercial',         'category': 'Bridging / Property', 'product': 'Bridging & Commercial',     'keywords': ['interbay']},
    {'name': 'Funding 365',                 'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['funding 365']},
    {'name': 'Affirmative Finance',         'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['affirmative finance']},
    {'name': 'Aria Finance',                'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['aria finance']},
    # ── DEVELOPMENT FINANCE ──
    {'name': 'Atelier Capital',             'category': 'Development Finance', 'product': 'Development',               'keywords': ['atelier capital']},
    {'name': 'CrowdProperty',               'category': 'Development Finance', 'product': 'P2P Development',           'keywords': ['crowdproperty']},
    {'name': 'Blend Network',               'category': 'Development Finance', 'product': 'P2P Development',           'keywords': ['blend network']},
    {'name': 'CapitalRise',                 'category': 'Development Finance', 'product': 'P2P Property',              'keywords': ['capitalrise']},
    {'name': 'Downing',                     'category': 'Development Finance', 'product': 'Development',               'keywords': ['downing']},
    # ── CORPORATE / GROWTH ──
    {'name': 'FSE Group',                   'category': 'Corporate / Growth',  'product': 'Growth Finance',            'keywords': ['fse group', 'fse']},
    {'name': 'Mercia',                      'category': 'Corporate / Growth',  'product': 'Venture / Growth',          'keywords': ['mercia']},
    {'name': 'Triple Point',                'category': 'Corporate / Growth',  'product': 'Venture Debt',              'keywords': ['triple point']},
    # ── HIGH STREET BANKS ──
    {'name': 'Barclays',                    'category': 'High Street Bank',    'product': 'Full Service',              'keywords': ['barclays', 'bcard commercial', 'barclaycard']},
    {'name': 'HSBC',                        'category': 'High Street Bank',    'product': 'Full Service',              'keywords': ['hsbc']},
    {'name': 'Lloyds Bank',                 'category': 'High Street Bank',    'product': 'Full Service',              'keywords': ['lloyds bank']},
    {'name': 'NatWest',                     'category': 'High Street Bank',    'product': 'Full Service',              'keywords': ['natwest']},
    {'name': 'Santander',                   'category': 'High Street Bank',    'product': 'Full Service',              'keywords': ['santander']},
    {'name': 'Bank of Scotland',            'category': 'High Street Bank',    'product': 'Full Service',              'keywords': ['bank of scotland']},
    {'name': 'Clydesdale Bank',             'category': 'High Street Bank',    'product': 'Full Service',              'keywords': ['clydesdale']},
    {'name': 'Yorkshire Bank',              'category': 'High Street Bank',    'product': 'Full Service',              'keywords': ['yorkshire bank']},
    {'name': 'Danske Bank',                 'category': 'High Street Bank',    'product': 'NI Lending',                'keywords': ['danske bank']},
    {'name': 'Bank of Ireland UK',          'category': 'High Street Bank',    'product': 'NI Lending',                'keywords': ['bank of ireland']},
    {'name': 'AIB Group UK',                'category': 'High Street Bank',    'product': 'NI Lending',                'keywords': ['aib', 'first trust']},
    {'name': 'Ulster Bank',                 'category': 'High Street Bank',    'product': 'NI Lending',                'keywords': ['ulster bank']},
    # ── CREDIT CARDS ──
    {'name': 'American Express',            'category': 'Credit Card',         'product': 'Business Credit Card',      'keywords': ['american express', 'amex']},
    {'name': 'Barclaycard',                 'category': 'Credit Card',         'product': 'Business Credit Card',      'keywords': ['barclaycard', 'bcard']},
    {'name': 'Capital One',                 'category': 'Credit Card',         'product': 'Business Credit Card',      'keywords': ['capital one']},
    {'name': 'MBNA',                        'category': 'Credit Card',         'product': 'Credit Card',              'keywords': ['mbna']},
    # ── GOVERNMENT ──
    {'name': 'British Business Bank',       'category': 'Government',          'product': 'Guarantee Schemes',         'keywords': ['british business bank']},
    {'name': 'Start Up Loans Company',      'category': 'Government',          'product': 'Start-Up Finance',          'keywords': ['start up loans', 'startup loans']},
    {'name': 'Homes England',               'category': 'Government',          'product': 'Housing / Development',     'keywords': ['homes england']},
    # ── NEW: UNSECURED / REVOLVING / FINTECH ──
    {'name': 'Bizlend',                     'category': 'Unsecured Lending',   'product': 'Short-Term Loan',           'keywords': ['bizlend']},
    {'name': 'Haogen Finance',              'category': 'Unsecured Lending',   'product': 'Business Loan',             'keywords': ['haogen']},
    {'name': 'NCF Finance',                 'category': 'Unsecured Lending',   'product': 'Business Finance',          'keywords': ['ncf finance', 'ncf']},
    {'name': 'Invocap',                     'category': 'Unsecured Lending',   'product': 'Revenue-Based',             'keywords': ['invocap']},
    {'name': 'Multifi',                     'category': 'Unsecured Lending',   'product': 'B2B BNPL / Credit',         'keywords': ['multifi']},
    {'name': 'Lendco',                      'category': 'Unsecured Lending',   'product': 'Business Loan',             'keywords': ['lendco']},
    {'name': 'Lendhub',                     'category': 'Unsecured Lending',   'product': 'Business Loan',             'keywords': ['lendhub']},
    {'name': 'BloomSmith',                  'category': 'Unsecured Lending',   'product': 'Tax / VAT Funding',         'keywords': ['bloomsmith']},
    {'name': 'Colenko',                     'category': 'Unsecured Lending',   'product': 'Business Loan',             'keywords': ['colenko']},
    {'name': 'NUbnk / OFFA',               'category': 'Unsecured Lending',   'product': 'Embedded Finance',          'keywords': ['nubnk', 'offa']},
    {'name': '4Syte',                       'category': 'Unsecured Lending',   'product': 'Business Finance',          'keywords': ['4syte']},
    {'name': 'Finsec',                      'category': 'Unsecured Lending',   'product': 'Business Finance',          'keywords': ['finsec']},
    {'name': 'Lakeshield',                  'category': 'Unsecured Lending',   'product': 'Business Loan',             'keywords': ['lakeshield']},
    # ── NEW: ASSET FINANCE ──
    {'name': 'Federal Capital',             'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['federal capital', 'federal capita']},
    {'name': 'LDF Finance',                 'category': 'Asset Finance',       'product': 'Asset / Vehicle Finance',   'keywords': ['ldf finance', 'ldf']},
    {'name': 'BPCE Equipment Solutions',    'category': 'Asset Finance',       'product': 'Equipment Finance',         'keywords': ['bpce']},
    {'name': 'Helmsley Acceptances',        'category': 'Asset Finance',       'product': 'Asset Finance',             'keywords': ['helmsley']},
    {'name': 'Horizon Energy Ventures',     'category': 'Asset Finance',       'product': 'Energy Asset Finance',      'keywords': ['horizon energy']},
    # ── NEW: INVOICE FINANCE ──
    {'name': 'Factored',                    'category': 'Invoice Finance',     'product': 'Factoring',                 'keywords': ['factored']},
    {'name': 'FlexABL',                     'category': 'Invoice Finance',     'product': 'ABL',                       'keywords': ['flexabl']},
    # ── NEW: BRIDGING / PROPERTY ──
    {'name': 'Alternative Bridging Corp',   'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['alternative bridging']},
    {'name': 'Devon & Cornwall Securities', 'category': 'Bridging / Property', 'product': 'Bridging',                  'keywords': ['devon & cornwall', 'devon and cornwall']},
    {'name': 'Landbay',                     'category': 'Bridging / Property', 'product': 'BTL Mortgages',             'keywords': ['landbay']},
    {'name': 'Proplend',                    'category': 'Bridging / Property', 'product': 'P2P Property',              'keywords': ['proplend']},
    {'name': 'Salboy Build Partner',        'category': 'Bridging / Property', 'product': 'Development',               'keywords': ['salboy']},
    # ── NEW: CHALLENGER BANK ──
    {'name': 'Cumberland Building Society', 'category': 'Challenger Bank',     'product': 'Savings & Mortgages',       'keywords': ['cumberland']},
]

# ============================================================
# DEBT COLLECTION / ENFORCEMENT REGISTRY
# ============================================================
# Presence of debt collection agencies on a bank statement is a
# CRITICAL red flag — indicates unpaid debts being pursued.

DEBT_COLLECTION_REGISTRY = [
    {'name': 'HCCI Credit Services',        'keywords': ['hcci']},
    {'name': 'Lowell Financial',            'keywords': ['lowell']},
    {'name': 'Intrum',                      'keywords': ['intrum']},
    {'name': 'PRA Group',                   'keywords': ['pra group']},
    {'name': 'Hoist Finance',               'keywords': ['hoist finance', 'hoist']},
    {'name': 'Cabot Financial',             'keywords': ['cabot financial', 'cabot']},
    {'name': 'Arrow Global',                'keywords': ['arrow global']},
    {'name': 'Moorcroft Debt Recovery',     'keywords': ['moorcroft']},
    {'name': 'Zinc Group',                  'keywords': ['zinc group']},
    {'name': 'BPF Collections',             'keywords': ['bpf collections']},
    {'name': 'Arvato Financial Solutions',  'keywords': ['arvato']},
    {'name': 'Capquest',                    'keywords': ['capquest']},
    {'name': 'Creditfix',                   'keywords': ['creditfix']},
    {'name': 'Excel Civil Enforcement',     'keywords': ['excel civil', 'excel enforcement']},
    {'name': 'Marston Holdings',            'keywords': ['marston holdings', 'marston']},
    {'name': 'Jacobs Enforcement',          'keywords': ['jacobs enforcement']},
    {'name': 'High Court Enforcement',      'keywords': ['high court enforcement', 'hce group']},
    {'name': 'Advantis Credit',             'keywords': ['advantis']},
    {'name': 'Wescot Credit Services',      'keywords': ['wescot']},
    {'name': 'Bristow & Sutor',             'keywords': ['bristow & sutor', 'bristow and sutor']},
    {'name': 'Rossendales',                 'keywords': ['rossendales']},
    {'name': 'Newlyn',                      'keywords': ['newlyn']},
    {'name': 'Drydensfairfax',              'keywords': ['drydensfairfax', 'drydens']},
    {'name': 'Philips & Cohen',             'keywords': ['philips & cohen', 'philips and cohen']},
]

# Fuzzy keywords for suspected-lender detection (checked if no static match)
LENDER_FUZZY_KEYWORDS = [
    'loan', 'loans', 'finance', 'financial', 'lending', 'lend', 'capital',
    'credit', 'funding', 'funded', 'funder', 'cash advance', 'merchant cash',
    'factor', 'factoring', 'factors', 'invoice finance', 'invoice discounting',
    'asset finance', 'leasing', 'lease', 'hire purchase', 'bridging',
    'bridge loan', 'revolving', 'drawdown', 'facility', 'repayment',
    'instalment', 'installment', 'settlement', 'refinance', 'mortgage',
    'secured loan', 'unsecured loan', 'debt', 'advance', 'overdraft',
    'credit line', 'creditline', 'trade finance', 'supply chain finance',
    'purchase order finance', 'development finance', 'mezzanine',
    'venture debt', 'growth loan', 'working capital', 'business loan',
    'term loan', 'short term loan', 'credit card',
]


def match_lender(description):
    """Check description against static lender registry. Returns lender dict or None."""
    d = description.lower()
    for lender in LENDER_REGISTRY:
        if any(kw in d for kw in lender['keywords']):
            return lender
    return None


# Phrases that contain fuzzy keywords but are NOT lenders (false positives)
FUZZY_EXCLUSIONS = [
    'automated credit',       # standard bank transfer type
    'credit interest',        # bank interest payment
    'credit received',        # generic bank descriptor
    'credit transfer',        # standard bank transfer type
    'bank credit',            # generic bank descriptor
    'gocardless',             # payment processor, not a lender
    'capital gains',          # tax-related, not a lender
    'working tax credit',     # HMRC benefit payment
    'universal credit',       # DWP benefit payment
    'child tax credit',       # HMRC benefit payment
    'pension credit',         # DWP benefit payment
    'credit union',           # savings institution, not commercial lender
    'credit suisse',          # investment bank, not SME lender
    'credit card payment',    # generic card payment descriptor
]


def match_suspected_lender(description):
    """Check description against fuzzy keywords. Returns True if suspected lender."""
    d = description.lower()
    if any(excl in d for excl in FUZZY_EXCLUSIONS):
        return False
    return any(kw in d for kw in LENDER_FUZZY_KEYWORDS)


# ============================================================
# BOUNCED / FAILED PAYMENT DETECTION
# ============================================================

# Layer 1: Exact string matching (high confidence)
EXACT_BOUNCED_PATTERNS = [
    'unpaid dd', 'unpaid d/d', 'unpaid direct debit', 'unpaid ddr',
    'unp ddr', 'unp dd', 'd/d unpd', 'unpd dd', 'unpadd',
    'returned dd', 'returned d/d', 'returned direct debit',
    'd/d returned', 'direct debit returned', 'ddr returned',
    'failed direct debit', 'failed payment', 'failed dd',
    'unpaid s/o', 'returned sto', 'so unpaid', 'rev sto',
    'unpaid item', 'returned item', 'refer to payer',
]

EXACT_FEE_PATTERNS = [
    'unpaid item fee', 'returned item fee', 'rtn item chg',
    'unarranged od fee', 'unauth od chg', 'excess borrowing fee',
    'paid referral', 'referral fee', 'emergency borrowing',
    'unpaid transaction fee', 'unpaid transaction charge',
    'unpadd fee', 'unauth borrow',
]

EXACT_OVERDRAFT_COST_PATTERNS = [
    'o/draft interest', 'overdraft interest', 'overdraft fee',
    'debit interest', 'service charge', 'arrangement fee',
    'excess fee', 'unauthorised borrowing',
]

# Layer 2: Tokenised fuzzy matching (medium confidence)
FUZZY_GROUP_A = {'unpaid', 'unpd', 'unp', 'returned', 'return', 'rtn',
                 'failed', 'refused', 'rejected', 'bounced', 'rev',
                 'recalled', 'reversed'}
FUZZY_GROUP_B = {'dd', 'ddr', 'direct', 'debit', 's/o', 'sto',
                 'standing', 'order', 'payment', 'item', 'transaction'}


def _tokenise(text):
    return set(re.split(r'[\s/\-]+', text.lower().strip()))


def detect_bounced_payments(transactions):
    """Three-layer detection of bounced/failed payments and bank stress fees."""
    confirmed_bounced = []
    confirmed_fees = []
    confirmed_od_costs = []
    suspected_bounced = []

    for tx in transactions:
        d = tx['description'].lower()
        tokens = _tokenise(tx['description'])

        # Layer 1: Exact pattern matching
        is_exact_bounced = any(p in d for p in EXACT_BOUNCED_PATTERNS)
        is_exact_fee = any(p in d for p in EXACT_FEE_PATTERNS)
        is_exact_od = any(p in d for p in EXACT_OVERDRAFT_COST_PATTERNS)

        if is_exact_bounced:
            confirmed_bounced.append({**tx, '_detection': 'exact_match', '_confidence': 'high'})
        elif is_exact_fee:
            confirmed_fees.append({**tx, '_detection': 'exact_match', '_confidence': 'high'})
        elif is_exact_od:
            confirmed_od_costs.append({**tx, '_detection': 'exact_match', '_confidence': 'high'})
        else:
            # Layer 2: Fuzzy token matching
            has_a = bool(tokens & FUZZY_GROUP_A)
            has_b = bool(tokens & FUZZY_GROUP_B)
            if has_a and has_b:
                suspected_bounced.append({**tx, '_detection': 'fuzzy_match', '_confidence': 'medium'})

    return {
        'confirmed_bounced': confirmed_bounced,
        'confirmed_fees': confirmed_fees,
        'confirmed_od_costs': confirmed_od_costs,
        'suspected_bounced': suspected_bounced,
        'total_confirmed': len(confirmed_bounced) + len(confirmed_fees),
        'total_suspected': len(suspected_bounced),
    }


# ============================================================
# HMRC NDDS / TIME TO PAY DETECTION
# ============================================================
# HMRC has two direct debit systems on bank statements:
#   HMRC SDDS — recurring auto-collection (PAYE via FPS). Normal.
#   HMRC NDDS — one-off direct debits (Corp Tax, SA, PAYE, VAT).
#              Also used for TTP instalment arrangements.
#
# A single HMRC NDDS payment is routine (paying Corp Tax or SA).
# A TTP shows as REPEATED HMRC NDDS payments — typically monthly,
# at fixed/similar amounts, on non-standard dates.
#
# Detection strategy:
#   - 'time to pay', 'ttp', 'debt management' in description → immediate flag
#   - 3+ HMRC NDDS payments in the period → flag as suspected TTP
#   - 1-2 HMRC NDDS payments → normal, not flagged

HMRC_TTP_EXPLICIT = ['time to pay', 'ttp', 'debt management']

def detect_hmrc_ttp(transactions):
    """Detect HMRC Time to Pay / NDDS arrangements.
    
    Distinguishes routine HMRC NDDS payments (Corp Tax, SA) from
    repeated instalment patterns that indicate a TTP arrangement.
    """
    explicit_hits = []
    ndds_payments = []

    for tx in transactions:
        d = tx['description'].lower()
        if 'hmrc' not in d:
            continue
        # Explicit TTP language — always flag
        if any(p in d for p in HMRC_TTP_EXPLICIT):
            explicit_hits.append(tx)
        # Collect all HMRC NDDS payments (outflows only)
        elif 'ndds' in d and tx.get('money_out', 0) > 0:
            ndds_payments.append(tx)

    # 3+ HMRC NDDS outbound payments suggests TTP instalments
    # (routine Corp Tax / SA would be 1-2 per period)
    suspected_ttp = ndds_payments if len(ndds_payments) >= 3 else []

    all_hits = explicit_hits + suspected_ttp
    return {
        'found': len(all_hits) > 0,
        'count': len(all_hits),
        'transactions': all_hits,
        'explicit': len(explicit_hits) > 0,
        'ndds_count': len(ndds_payments),
        'pattern_based': len(suspected_ttp) > 0 and len(explicit_hits) == 0,
    }


# ============================================================
# GAMBLING & SANCTIONS (unchanged — already generic)
# ============================================================

GAMBLING_KEYWORDS = [
    'bet365', 'betfair', 'paddy power', 'william hill', 'ladbrokes',
    'coral', 'sky bet', 'betway', 'unibet', '888sport', 'betfred',
    'tombola', 'lottoland', 'camelot', 'national lottery', 'casino',
    'jackpot', 'poker stars', 'bingo', 'grosvenor', 'betvictor'
]

SANCTIONED_COUNTRIES = [
    'russia', 'iran', 'north korea', 'dprk', 'myanmar', 'belarus',
    'syria', 'venezuela', 'cuba', 'sudan', 'eritrea', 'somalia',
    'liberia', 'zimbabwe'
]

MIDDLE_EAST_KEYWORDS = [
    'saudi', 'jeddah', 'riyadh', 'bahrain', 'ziina', 'visitsvisa',
    'dubai', 'abu dhabi', 'uae', 'qatar', 'kuwait', 'oman'
]


# ============================================================
# CATEGORISATION ENGINE — fully generic, no hardcoded names
# ============================================================

def categorise(description, money_out, money_in, account_name='', connected_names=None):
    """
    Categorise a transaction. Uses lender registry, connected party names,
    and generic keyword matching. No client-specific hardcoding.
    """
    d = description.lower()
    connected_names = connected_names or []

    # ── INFLOWS ──
    if money_in > 0:
        # Lender drawdown (not trading income)
        if match_lender(description):
            return 'Unsecured Loan Drawdowns'
        # HMRC refunds
        if 'hmrc' in d and ('vat' in d or 'repay' in d or 'refund' in d):
            return 'HMRC Refunds (VAT)'
        # Connected party inflows
        if connected_names and any(cn in d for cn in connected_names):
            return 'Connected Party Receipts'
        # Returned/reversed DDs credited back
        if any(p in d for p in ['returned dd', 'returned d/d', 'returned direct debit',
                                'unpaid direct debit', 'unpaid dd', 'unpaid d/d']):
            return 'Returned / Reversed Payments'
        # Default inflow
        return 'Other Trading Receipts'

    # ── OUTFLOWS ──
    # Lender repayments
    lender = match_lender(description)
    if lender:
        cat = lender.get('category', '')
        if cat == 'Asset Finance':
            return 'Asset Finance Repayments'
        return 'Unsecured Loan Repayments'
    # HMRC (generic — no client-specific refs)
    if 'hmrc' in d and any(w in d for w in ['paye', 'nic', 'cumbernauld', 'shipley', 'accounts office']):
        return 'HMRC PAYE / NIC'
    if 'hmrc' in d:
        return 'HMRC Payments'
    # Pension (generic providers)
    if any(x in d for x in ['nest', 'peoplespartnership', 'peoples partnership',
                            'now pensions', 'smart pension', 'aviva pension',
                            'royal london', 'scottish widows', 'aegon']):
        return 'Pension'
    if 'sipp' in d or 'pension' in d:
        return 'Pension'
    # Connected party outflows
    if connected_names and any(cn in d for cn in connected_names):
        return 'Director/Connected Party Payments Out'
    # Bounced/failed payment fees
    if any(p in d for p in EXACT_BOUNCED_PATTERNS + EXACT_FEE_PATTERNS):
        return 'Unpaid Item Fees'
    # Overdraft / bank charges
    if any(p in d for p in EXACT_OVERDRAFT_COST_PATTERNS):
        return 'Bank Charges & Subscriptions'
    # Generic subscriptions / utilities
    if any(x in d for x in ['xero', 'gocardless', 'zoom', 'quickbooks', 'sage',
                            'microsoft', 'google', 'amazon web', 'mailchimp',
                            'hubspot', 'slack', 'dropbox']):
        return 'Bank Charges & Subscriptions'
    return 'Other Outgoings'


CAT_INFLOW = [
    'Other Trading Receipts',
    'HMRC Refunds (VAT)',
    'Director/Connected Party Injections',
    'Connected Party Receipts',
    'Unsecured Loan Drawdowns',
    'Returned / Reversed Payments',
]
CAT_OUTFLOW = [
    'Unsecured Loan Repayments',
    'Asset Finance Repayments',
    'HMRC PAYE / NIC',
    'HMRC Payments',
    'Pension',
    'Wages / Payroll',
    'Rent',
    'Bank Charges & Subscriptions',
    'Unpaid Item Fees',
    'Director/Connected Party Payments Out',
    'Other Outgoings',
]


# ============================================================
# CONNECTED PARTY DETECTION — dynamic, fuzzy
# ============================================================

def _normalise_name(name):
    """Normalise company/person name for fuzzy matching."""
    n = name.lower().strip()
    # Strip common suffixes
    for suffix in [' limited', ' ltd', ' plc', ' llp', ' lp', ' inc',
                   ' corp', ' group', ' holdings', ' uk', ' (uk)']:
        n = n.replace(suffix, '')
    return n.strip()


def _name_tokens(name):
    """Split name into significant tokens, dropping short/common words."""
    tokens = set(re.split(r'[\s\-&,\.]+', _normalise_name(name)))
    stop = {'the', 'and', 'of', 'for', 'in', 'at', 'mr', 'mrs', 'ms', 'dr', 'a'}
    return {t for t in tokens if len(t) > 1 and t not in stop}


def build_connected_names(account_name, director_names=None):
    """
    Build list of lowercased name fragments for connected party matching.
    account_name: from statement metadata
    director_names: list of strings from CH API (optional)
    """
    names = []
    # Account holder name fragments
    if account_name:
        norm = _normalise_name(account_name)
        if norm:
            names.append(norm)
            # Also add individual significant tokens (e.g. 'mobius' from 'Mobius Industries')
            for tok in _name_tokens(account_name):
                if len(tok) >= 4:  # Only tokens 4+ chars to avoid false positives
                    names.append(tok)
    # Director/PSC names
    if director_names:
        for dn in director_names:
            norm = _normalise_name(dn)
            if norm:
                names.append(norm)
                # Add surname (last token) if multi-word
                parts = norm.split()
                if len(parts) >= 2 and len(parts[-1]) >= 4:
                    names.append(parts[-1])
    return list(set(names))


def find_connected_parties(transactions, connected_names):
    """Find connected party transactions using dynamic name matching."""
    out = []
    inp = []
    for tx in transactions:
        d = tx['description'].lower()
        matched_name = None
        for cn in connected_names:
            if cn in d:
                matched_name = cn
                break
        if matched_name:
            entry = {**tx, '_matched_name': matched_name}
            if tx.get('money_out', 0) > 0:
                out.append(entry)
            if tx.get('money_in', 0) > 0:
                inp.append(entry)
    return out, inp


# ============================================================
# MERGE & PREPARE TRANSACTIONS
# ============================================================

def merge_statements(parsed_statements, connected_names=None):
    seen = set()
    all_txs = []
    account_name = ''
    if parsed_statements:
        account_name = parsed_statements[0].get('metadata', {}).get('account_name', '')

    for stmt in parsed_statements:
        for tx in stmt.get('transactions', []):
            key = (tx['date'], tx['description'], tx['money_out'], tx['money_in'])
            if key not in seen:
                seen.add(key)
                tx['category'] = categorise(
                    tx['description'], tx['money_out'], tx['money_in'],
                    account_name=account_name,
                    connected_names=connected_names,
                )
                # Tag lender matches
                lender = match_lender(tx['description'])
                tx['_lender'] = lender['name'] if lender else None
                tx['_suspected_lender'] = (
                    not lender and match_suspected_lender(tx['description'])
                )
                all_txs.append(tx)

    def parse_date(d):
        for fmt in ('%d/%m/%y', '%d/%m/%Y'):
            try:
                return datetime.strptime(d, fmt)
            except ValueError:
                continue
        return datetime.min
    all_txs.sort(key=lambda x: parse_date(x['date']))
    return all_txs


def get_statement_metadata(parsed_statements):
    meta_list = []
    for stmt in parsed_statements:
        m = stmt.get('metadata', {})
        start_str = m.get('statement_start', '')
        end_str   = m.get('statement_end', '')
        for fmt in ('%d/%m/%y', '%d/%m/%Y'):
            try:
                start = datetime.strptime(start_str, fmt)
                end   = datetime.strptime(end_str, fmt)
                meta_list.append({
                    'account_name':    m.get('account_name', ''),
                    'account_number':  m.get('account_number', ''),
                    'sort_code':       m.get('sort_code', ''),
                    'start':           start,
                    'end':             end,
                    'opening_balance': m.get('opening_balance', 0),
                    'closing_balance': m.get('closing_balance', 0),
                    'filename':        stmt.get('_filename', ''),
                })
                break
            except ValueError:
                continue
    meta_list.sort(key=lambda x: x['start'])
    return meta_list


# ============================================================
# MONTHLY BUCKETING
# ============================================================

def assign_month_index(date_str, period_start, n_months):
    for fmt in ('%d/%m/%y', '%d/%m/%Y'):
        try:
            d = datetime.strptime(date_str, fmt)
            months_diff = (d.year - period_start.year) * 12 + (d.month - period_start.month)
            if 0 <= months_diff < n_months:
                return months_diff
            return max(0, min(months_diff, n_months - 1))
        except ValueError:
            continue
    return 0


def build_monthly_buckets(transactions, period_start, n_months):
    monthly = {cat: [0.0] * n_months for cat in CAT_INFLOW + CAT_OUTFLOW}
    monthly_in  = [0.0] * n_months
    monthly_out = [0.0] * n_months
    for tx in transactions:
        idx = assign_month_index(tx['date'], period_start, n_months)
        cat = tx.get('category', 'Other Outgoings')
        if tx['money_in'] > 0:
            if cat in monthly:
                monthly[cat][idx] += tx['money_in']
            monthly_in[idx] += tx['money_in']
        if tx['money_out'] > 0:
            if cat in monthly:
                monthly[cat][idx] += tx['money_out']
            monthly_out[idx] += tx['money_out']
    return monthly, monthly_in, monthly_out


# ============================================================
# DAILY BALANCE SERIES — fixed for overdraft accounts
# ============================================================

def build_daily_series(transactions, opening_balance, period_start, period_end):
    date_bal = {}
    for tx in transactions:
        for fmt in ('%d/%m/%y', '%d/%m/%Y'):
            try:
                d = datetime.strptime(tx['date'], fmt)
                # Record ALL balances including negative (overdraft)
                if tx.get('balance', 0) != 0:
                    date_bal[d] = tx['balance']
                break
            except ValueError:
                continue
    daily = []
    current = opening_balance
    d = period_start
    while d <= period_end:
        if d in date_bal:
            current = date_bal[d]
        daily.append((d, current))
        d += timedelta(days=1)
    return daily


# ============================================================
# INTRA-MONTH PROFILE
# ============================================================

def build_intramonth_profile(daily_series, meta_list):
    def week_bucket(day):
        if day <= 7:  return 0
        if day <= 14: return 1
        if day <= 21: return 2
        return 3
    daily_map = {d: b for d, b in daily_series}
    intramonth = []
    for meta in meta_list:
        buckets = [[], [], [], []]
        d = meta['start']
        while d <= meta['end']:
            bal = daily_map.get(d)
            if bal is not None:
                buckets[week_bucket(d.day)].append(bal)
            d += timedelta(days=1)
        avg_buckets = [round(sum(b) / len(b)) if b else None for b in buckets]
        intramonth.append(avg_buckets)
    avg_overall = []
    for wk in range(4):
        vals = [intramonth[m][wk] for m in range(len(intramonth)) if intramonth[m][wk] is not None]
        avg_overall.append(round(sum(vals) / len(vals)) if vals else 0)
    return intramonth, avg_overall


# ============================================================
# LOAN AFFORDABILITY
# ============================================================

def pmt_to_principal(monthly_payment, r=MONTHLY_RATE, n=N_MONTHS):
    if monthly_payment <= 0:
        return 0
    pv_factor = (1 - (1 + r) ** (-n)) / r
    return monthly_payment * pv_factor


def principal_to_pmt(principal, r=MONTHLY_RATE, n=N_MONTHS):
    return principal * r / (1 - (1 + r) ** (-n))


def calc_affordability(monthly_in, monthly_out, anomalous_txs=None, month_labels=None,
                       avg_daily_balance=0):
    """Calculate both unadjusted and adjusted affordability.
    Now also considers persistent overdraft status via avg_daily_balance.
    """
    n = len(monthly_in)

    # --- UNADJUSTED (all receipts included) ---
    unadj_avg_in_full  = sum(monthly_in) / n
    unadj_avg_out_full = sum(monthly_out) / n
    unadj_surplus_full = unadj_avg_in_full - unadj_avg_out_full
    unadj_avg_in_3m    = sum(monthly_in[-3:]) / 3
    unadj_avg_out_3m   = sum(monthly_out[-3:]) / 3
    unadj_surplus_3m   = unadj_avg_in_3m - unadj_avg_out_3m

    unadj_max_pmt_full = max(0, unadj_surplus_full / DSCR_BUFFER)
    unadj_max_pmt_3m   = max(0, unadj_surplus_3m   / DSCR_BUFFER)
    unadj_max_loan_full_dscr = min(MAX_LOAN, pmt_to_principal(unadj_max_pmt_full))
    unadj_max_loan_3m_dscr   = min(MAX_LOAN, pmt_to_principal(unadj_max_pmt_3m))
    unadj_max_loan_full_zero = min(MAX_LOAN, pmt_to_principal(max(0, unadj_surplus_full)))
    unadj_max_loan_3m_zero   = min(MAX_LOAN, pmt_to_principal(max(0, unadj_surplus_3m)))

    # --- ADJUSTED (anomalous receipts excluded) ---
    adj_in = list(monthly_in)
    if anomalous_txs and month_labels:
        for atx in anomalous_txs:
            amt = atx['money_in']
            midx = atx.get('_month_idx')
            if midx is not None and 0 <= midx < n:
                adj_in[midx] = max(0, adj_in[midx] - amt)

    adj_avg_in_full  = sum(adj_in) / n
    adj_avg_out_full = sum(monthly_out) / n
    adj_surplus_full = adj_avg_in_full - adj_avg_out_full
    adj_avg_in_3m    = sum(adj_in[-3:]) / 3
    adj_avg_out_3m   = sum(monthly_out[-3:]) / 3
    adj_surplus_3m   = adj_avg_in_3m - adj_avg_out_3m

    adj_max_pmt_full = max(0, adj_surplus_full / DSCR_BUFFER)
    adj_max_pmt_3m   = max(0, adj_surplus_3m   / DSCR_BUFFER)
    adj_max_loan_full_dscr = min(MAX_LOAN, pmt_to_principal(adj_max_pmt_full))
    adj_max_loan_3m_dscr   = min(MAX_LOAN, pmt_to_principal(adj_max_pmt_3m))
    adj_max_loan_full_zero = min(MAX_LOAN, pmt_to_principal(max(0, adj_surplus_full)))
    adj_max_loan_3m_zero   = min(MAX_LOAN, pmt_to_principal(max(0, adj_surplus_3m)))

    # --- OVERDRAFT WARNING ---
    persistent_overdraft = avg_daily_balance < 0
    overdraft_warning = None
    if persistent_overdraft:
        overdraft_warning = (
            f'Account operates on permanent overdraft (avg daily balance {fmt_money(avg_daily_balance)}). '
            f'Reported surplus of {fmt_money(round(adj_surplus_full))} represents reduction in overdraft depth, '
            f'not free cash available for new debt service. Recommend £0 affordability.'
        )

    pmt_10k = principal_to_pmt(10_000)
    pmt_25k = principal_to_pmt(25_000)
    pmt_50k = principal_to_pmt(50_000)

    total_excluded = sum(atx['money_in'] for atx in (anomalous_txs or []))

    return {
        # Unadjusted
        'unadj_avg_in_full':        round(unadj_avg_in_full),
        'unadj_avg_out_full':       round(unadj_avg_out_full),
        'unadj_surplus_full':       round(unadj_surplus_full),
        'unadj_avg_in_3m':          round(unadj_avg_in_3m),
        'unadj_avg_out_3m':         round(unadj_avg_out_3m),
        'unadj_surplus_3m':         round(unadj_surplus_3m),
        'unadj_max_pmt_full':       round(unadj_max_pmt_full),
        'unadj_max_pmt_3m':         round(unadj_max_pmt_3m),
        'unadj_max_loan_full_dscr': round(unadj_max_loan_full_dscr / 100) * 100,
        'unadj_max_loan_3m_dscr':   round(unadj_max_loan_3m_dscr   / 100) * 100,
        'unadj_max_loan_full_zero': round(unadj_max_loan_full_zero  / 100) * 100,
        'unadj_max_loan_3m_zero':   round(unadj_max_loan_3m_zero    / 100) * 100,
        # Adjusted
        'avg_in_full':        round(adj_avg_in_full),
        'avg_out_full':       round(adj_avg_out_full),
        'surplus_full':       round(adj_surplus_full),
        'avg_in_3m':          round(adj_avg_in_3m),
        'avg_out_3m':         round(adj_avg_out_3m),
        'surplus_3m':         round(adj_surplus_3m),
        'max_pmt_full':       round(adj_max_pmt_full),
        'max_pmt_3m':         round(adj_max_pmt_3m),
        'max_loan_full_dscr': round(adj_max_loan_full_dscr / 100) * 100,
        'max_loan_3m_dscr':   round(adj_max_loan_3m_dscr   / 100) * 100,
        'max_loan_full_zero': round(adj_max_loan_full_zero  / 100) * 100,
        'max_loan_3m_zero':   round(adj_max_loan_3m_zero    / 100) * 100,
        # Reference
        'pmt_10k':            round(pmt_10k),
        'pmt_25k':            round(pmt_25k),
        'pmt_50k':            round(pmt_50k),
        'annual_rate':        ANNUAL_RATE,
        'monthly_rate':       MONTHLY_RATE,
        'n_months':           N_MONTHS,
        'total_excluded':     round(total_excluded),
        # Overdraft
        'persistent_overdraft': persistent_overdraft,
        'overdraft_warning':    overdraft_warning,
    }


# ============================================================
# CREDIT FLAGS
# ============================================================

def check_gambling(transactions):
    hits = [t for t in transactions if any(k in t['description'].lower() for k in GAMBLING_KEYWORDS)]
    return {'found': len(hits) > 0, 'count': len(hits), 'transactions': hits}


def check_sanctions(transactions):
    sanction_hits = []
    middle_east   = []
    for t in transactions:
        d = t['description'].lower()
        for sc in SANCTIONED_COUNTRIES:
            if sc in d:
                sanction_hits.append(t)
        if any(k in d for k in MIDDLE_EAST_KEYWORDS):
            middle_east.append(t)
    return {'sanction_hits': sanction_hits, 'middle_east_txs': middle_east, 'clean': len(sanction_hits) == 0}


def check_salary_consistency(transactions, month_labels):
    """Generic HMRC PAYE detection — no client-specific refs."""
    n = len(month_labels)
    paye_by_month = [0.0] * n
    for tx in transactions:
        d = tx['description'].lower()
        if 'hmrc' in d and any(w in d for w in ['paye', 'nic', 'cumbernauld', 'shipley', 'accounts office']):
            for fmt in ('%d/%m/%y', '%d/%m/%Y'):
                try:
                    dt = datetime.strptime(tx['date'], fmt)
                    label = dt.strftime('%b-%y')
                    if label in month_labels:
                        idx = month_labels.index(label)
                        paye_by_month[idx] += tx['money_out']
                    break
                except ValueError:
                    continue
    nonzero = [v for v in paye_by_month if v > 0]
    if len(nonzero) >= 2:
        variance_pct = (max(nonzero) - min(nonzero)) / min(nonzero) * 100
    else:
        variance_pct = 0
    return {
        'paye_by_month': paye_by_month,
        'variance_pct':  round(variance_pct, 1),
        'consistent':    variance_pct < 10,
        'month_labels':  month_labels
    }


def check_low_balance_days(daily_series):
    """Fixed: now correctly handles negative (overdraft) balances."""
    negative   = [(d.strftime('%d/%m/%y'), b) for d, b in daily_series if b < 0]
    below_2k   = [(d.strftime('%d/%m/%y'), b) for d, b in daily_series if 0 <= b < 2000]
    below_5k   = [(d.strftime('%d/%m/%y'), b) for d, b in daily_series if 0 <= b < 5000]
    return {
        'negative_count':  len(negative),
        'negative_days':   negative,
        'below_5k_count':  len(below_5k),
        'below_2k_count':  len(below_2k),
        'below_5k_days':   below_5k,
        'below_2k_days':   below_2k,
        'lowest':          min(daily_series, key=lambda x: x[1]) if daily_series else None
    }


def find_lenders(transactions):
    """Dynamic lender detection using full registry + suspected lender fuzzy matching."""
    confirmed = {}
    suspected = {}

    for tx in transactions:
        d = tx['description'].lower()

        # Check static registry
        lender = match_lender(tx['description'])
        if lender:
            key = lender['name']
            if key not in confirmed:
                confirmed[key] = {
                    'name': lender['name'],
                    'product': lender['product'],
                    'category': lender['category'],
                    'total_out': 0, 'total_in': 0,
                    'transactions_out': [], 'transactions_in': [],
                    'count_out': 0, 'count_in': 0,
                }
            if tx.get('money_out', 0) > 0:
                confirmed[key]['total_out'] += tx['money_out']
                confirmed[key]['transactions_out'].append(tx)
                confirmed[key]['count_out'] += 1
            if tx.get('money_in', 0) > 0:
                confirmed[key]['total_in'] += tx['money_in']
                confirmed[key]['transactions_in'].append(tx)
                confirmed[key]['count_in'] += 1
            continue

        # Fuzzy keyword check for suspected lenders
        if match_suspected_lender(tx['description']):
            # Extract counterparty name (first 30 chars as proxy)
            short = tx['description'][:30].strip()
            if short not in suspected:
                suspected[short] = {
                    'name': short,
                    'product': 'Unknown — Manual Review',
                    'category': 'Suspected',
                    'total_out': 0, 'total_in': 0,
                    'transactions_out': [], 'transactions_in': [],
                    'count_out': 0, 'count_in': 0,
                }
            if tx.get('money_out', 0) > 0:
                suspected[short]['total_out'] += tx['money_out']
                suspected[short]['transactions_out'].append(tx)
                suspected[short]['count_out'] += 1
            if tx.get('money_in', 0) > 0:
                suspected[short]['total_in'] += tx['money_in']
                suspected[short]['transactions_in'].append(tx)
                suspected[short]['count_in'] += 1

    return {
        'confirmed': confirmed,
        'suspected': suspected,
    }


def find_debt_collectors(transactions):
    """Detect payments to/from known debt collection and enforcement agencies."""
    collectors = {}
    for tx in transactions:
        d = tx['description'].lower()
        for entry in DEBT_COLLECTION_REGISTRY:
            if any(kw in d for kw in entry['keywords']):
                key = entry['name']
                if key not in collectors:
                    collectors[key] = {
                        'name': entry['name'],
                        'total_out': 0, 'total_in': 0,
                        'transactions': [], 'count': 0,
                    }
                collectors[key]['transactions'].append(tx)
                collectors[key]['count'] += 1
                if tx.get('money_out', 0) > 0:
                    collectors[key]['total_out'] += tx['money_out']
                if tx.get('money_in', 0) > 0:
                    collectors[key]['total_in'] += tx['money_in']
                break  # one match per transaction
    return collectors


def find_top_transactions(transactions, n=5):
    top_in  = sorted([t for t in transactions if t['money_in'] > 0], key=lambda x: -x['money_in'])[:n]
    top_out = sorted([t for t in transactions if t['money_out'] > 0], key=lambda x: -x['money_out'])[:n]
    return top_in, top_out


# ============================================================
# MASTER ANALYTICS FUNCTION
# ============================================================

def run_analytics(parsed_statements, director_names=None):
    """
    Main analytics pipeline. Now accepts optional director_names from CH API
    for connected party detection.
    """
    meta_list = get_statement_metadata(parsed_statements)
    if not meta_list:
        return None

    period_start   = meta_list[0]['start']
    period_end     = meta_list[-1]['end']
    opening_bal    = meta_list[0]['opening_balance']
    closing_bal    = meta_list[-1]['closing_balance']
    account_name   = meta_list[0]['account_name']
    account_number = meta_list[0]['account_number']
    sort_code      = meta_list[0]['sort_code']

    # Build connected party names dynamically
    connected_names = build_connected_names(account_name, director_names)

    # Merge and categorise transactions
    transactions = merge_statements(parsed_statements, connected_names)

    # Month labels
    month_labels = []
    seen_months = set()
    for meta in meta_list:
        d = meta['start']
        while d <= meta['end']:
            label = d.strftime('%b-%y')
            if label not in seen_months:
                seen_months.add(label)
                month_labels.append(label)
            if d.month == 12:
                d = d.replace(year=d.year + 1, month=1, day=1)
            else:
                d = d.replace(month=d.month + 1, day=1)
    n_months = len(month_labels)

    # Monthly buckets
    monthly, monthly_in, monthly_out = build_monthly_buckets(transactions, period_start, n_months)
    closing_bals = [m['closing_balance'] for m in meta_list]

    # Daily balance series (fixed for overdrafts)
    daily_series = build_daily_series(transactions, opening_bal, period_start, period_end)
    daily_vals   = [b for _, b in daily_series]
    avg_bal_full = round(sum(daily_vals) / len(daily_vals)) if daily_vals else 0
    cutoff = period_end - timedelta(days=90)
    daily_3m = [b for d, b in daily_series if d >= cutoff]
    avg_bal_3m = round(sum(daily_3m) / len(daily_3m)) if daily_3m else 0

    # Intra-month profile
    intramonth_data, avg_intramonth = build_intramonth_profile(daily_series, meta_list)

    # Lender detection (full registry + fuzzy)
    lenders = find_lenders(transactions)

    # Debt collection / enforcement detection
    debt_collectors = find_debt_collectors(transactions)

    # Anomaly detection — large inflows + ALL lender drawdowns
    avg_monthly_in = sum(monthly_in) / n_months if n_months else 0
    anomalous_txs = []

    # Flag lender drawdowns as anomalous regardless of size
    for tx in transactions:
        if tx.get('money_in', 0) > 0 and tx.get('_lender'):
            for fmt in ('%d/%m/%y', '%d/%m/%Y'):
                try:
                    dt = datetime.strptime(tx['date'], fmt)
                    label = dt.strftime('%b-%y')
                    midx = month_labels.index(label) if label in month_labels else None
                    anomalous_txs.append({
                        **tx,
                        '_month_idx': midx,
                        '_reason': f'Lender drawdown ({tx["_lender"]}) — not trading income',
                    })
                    break
                except ValueError:
                    continue

    # Flag large inflows exceeding 2× avg (existing logic)
    already_flagged = {(a['date'], a['description']) for a in anomalous_txs}
    large_inflows = sorted(
        [t for t in transactions if t['money_in'] > avg_monthly_in * 2],
        key=lambda x: -x['money_in']
    )
    for tx in large_inflows:
        if (tx['date'], tx['description']) in already_flagged:
            continue
        for fmt in ('%d/%m/%y', '%d/%m/%Y'):
            try:
                dt = datetime.strptime(tx['date'], fmt)
                label = dt.strftime('%b-%y')
                midx = month_labels.index(label) if label in month_labels else None
                anomalous_txs.append({
                    **tx,
                    '_month_idx': midx,
                    '_reason': f'Exceeds 2× avg monthly inflow ({fmt_money(avg_monthly_in)})',
                })
                break
            except ValueError:
                continue

    # Legacy single-anomaly fields (backward compat)
    anomaly_amount    = 0
    anomaly_month_idx = None
    if large_inflows:
        biggest = large_inflows[0]
        anomaly_amount = biggest['money_in']
        for fmtstr in ('%d/%m/%y', '%d/%m/%Y'):
            try:
                dt = datetime.strptime(biggest['date'], fmtstr)
                label = dt.strftime('%b-%y')
                if label in month_labels:
                    anomaly_month_idx = month_labels.index(label)
                break
            except ValueError:
                continue

    # Affordability (with overdraft awareness)
    affordability = calc_affordability(
        monthly_in, monthly_out,
        anomalous_txs=anomalous_txs,
        month_labels=month_labels,
        avg_daily_balance=avg_bal_full,
    )

    # Credit checks
    gambling      = check_gambling(transactions)
    sanctions     = check_sanctions(transactions)
    salary        = check_salary_consistency(transactions, month_labels)
    low_balance   = check_low_balance_days(daily_series)
    top_in, top_out = find_top_transactions(transactions)
    connected_out, connected_in = find_connected_parties(transactions, connected_names)

    # Bounced payment detection (3-layer)
    bounced = detect_bounced_payments(transactions)

    # HMRC TTP detection
    hmrc_ttp = detect_hmrc_ttp(transactions)

    # Existing debt service — dynamic across ALL confirmed lenders
    confirmed_lenders = lenders.get('confirmed', {})
    existing_debt_service = sum(
        v['total_out'] / n_months for v in confirmed_lenders.values()
    ) if n_months else 0

    return {
        'account_name': account_name, 'account_number': account_number,
        'sort_code': sort_code,
        'period_start': period_start.strftime('%d/%m/%y'),
        'period_end': period_end.strftime('%d/%m/%y'),
        'opening_bal': opening_bal, 'closing_bal': closing_bal,
        'n_months': n_months, 'month_labels': month_labels,
        'meta_list': meta_list,
        'transactions': transactions, 'total_tx_count': len(transactions),
        'monthly': monthly, 'monthly_in': monthly_in, 'monthly_out': monthly_out,
        'closing_bals': closing_bals,
        'daily_series': [(d.strftime('%d/%m/%y'), b) for d, b in daily_series],
        'avg_bal_full': avg_bal_full, 'avg_bal_3m': avg_bal_3m,
        'intramonth_data': intramonth_data, 'avg_intramonth': avg_intramonth,
        'lenders': lenders, 'debt_collectors': debt_collectors, 'existing_debt_svc': round(existing_debt_service),
        'anomaly_amount': anomaly_amount,
        'anomaly_tx': large_inflows[0] if large_inflows else None,
        'anomaly_month_idx': anomaly_month_idx,
        'anomalous_txs': anomalous_txs,
        'avg_monthly_in': round(avg_monthly_in),
        'affordability': affordability,
        'gambling': gambling, 'sanctions': sanctions,
        'salary': salary, 'low_balance': low_balance,
        'bounced': bounced,
        'hmrc_ttp': hmrc_ttp,
        'top_in': top_in, 'top_out': top_out,
        'connected_out': connected_out, 'connected_in': connected_in,
        'connected_names': connected_names,
        # Legacy compat — report_builder still references failed_dds
        'failed_dds': {
            'count': bounced['total_confirmed'] + bounced['total_suspected'],
            'transactions': bounced['confirmed_bounced'] + bounced['suspected_bounced'],
        },
    }
