#!/usr/bin/env python3
"""Fail-closed opt-in affiliate card generator for a future approved deployment.

Never creates/guesses tracking URLs. This v3.17 ships with ads disabled.
Generated HTML is a fragment: never silently inserted into the financial table.
"""
import argparse,html,json,re
from pathlib import Path
from urllib.parse import urlparse

class AdPolicyError(ValueError):pass

ALLOWED_PLACEMENTS={'after-insights','career-guide-footer'}

def render(config):
    if not config.get('ads_enabled',False):return ''
    campaigns=config.get('campaigns')
    if not isinstance(campaigns,list) or not campaigns:
        raise AdPolicyError('No approved campaigns provided')
    disclosure=config.get('disclosure_template','')
    if not re.search(r'(^|\W)(PR|広告|アフィリエイト)(\W|$)',disclosure):
        raise AdPolicyError('Visible advertising disclosure missing')
    output=[];seen=set()
    for campaign in campaigns:
        slot=campaign.get('slot')
        url=campaign.get('tracking_url','')
        allowed=campaign.get('approved_domains',[])
        parsed=urlparse(url)
        if slot not in ALLOWED_PLACEMENTS:raise AdPolicyError('Unsupported placement')
        if campaign.get('advertiser_approved') is not True:
            raise AdPolicyError('Advertiser approval not confirmed')
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
            raise AdPolicyError('Unsafe ad URL')
        if parsed.hostname.lower() not in allowed:
            raise AdPolicyError('Tracking host not explicitly approved')
        key=(slot,url)
        if key in seen:raise AdPolicyError('Duplicate campaign')
        seen.add(key)
        label=campaign.get('label','')
        if not 2<=len(label)<=150:raise AdPolicyError('Ad title missing/oversized')
        description=campaign.get('description','')
        if len(description)>500:raise AdPolicyError('Ad description oversized')
        output.append('<aside class="mcl-sponsored" data-placement="'+html.escape(slot,quote=True)+'" aria-label="広告">'
            '<p class="mcl-ad-disclosure">'+html.escape(disclosure)+'</p>'
            '<a rel="sponsored nofollow noopener noreferrer" target="_blank" href="'+html.escape(url,quote=True)+'">'
            +html.escape(label)+'</a><p>'+html.escape(description)+'</p></aside>')
    return '\n'.join(output)

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',default='ad-placement-plan-v317.json')
    p.add_argument('--output',default='ad-staging-v317.html')
    a=p.parse_args()
    html_text=render(json.loads(Path(a.config).read_text(encoding='utf-8')))
    Path(a.output).write_text(html_text,encoding='utf-8')
    print('Ad staging ready: '+('no ads (disabled)' if not html_text else 'approved ad fragments'))
if __name__=='__main__':main()
