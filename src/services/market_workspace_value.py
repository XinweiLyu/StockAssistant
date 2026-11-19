"""Use the existing value workflow, with strict listing and currency bindings."""
from copy import deepcopy
from src.services.a_share_value_service import ValueResearchService
from src.services.market_workspace_financials import listing_binding,validate_listing_capital


class WorkspaceValueService(ValueResearchService):
    def _data(self,code):
        data=deepcopy(super()._data(code))
        attestation=self.assistant.repo.latest(self.profile,'listing_attestation',key=self.key(code))
        if attestation:
            data.setdefault('facts',[]).append(dict(fact_id=attestation['id'],source='user/listing_attestation',
                code=code,category='capital',available_at=attestation['observed_at'],
                observed_at=attestation['observed_at'],values=attestation))
        return data

    def _binding(self,stock,data):
        binding=super()._binding(stock,data)
        currency=self.assistant.market.value_metadata(stock['code'])['currency']
        anchor=(stock.get('quote') or {}).get('trade_date') or self.assistant.market.completed_day()
        saved=self.assistant.market.repo.get_state(self.profile,'listing-binding:'+stock['code'],{})
        binding['listing']=listing_binding(stock,anchor,currency,saved.get('fx'),saved.get('capital'))
        return binding

    def _quote(self,stock):
        quote=super()._quote(stock)
        quote.update(instrument_id=stock['code'],currency=stock.get('currency'),market=stock['market'],basis='raw')
        return quote

    def _eligibility(self,stock):
        result=super()._eligibility(stock)
        if stock.get('asset_type')!='stock':result.update(eligible=False,reason='该证券不是已核实普通企业股权')
        return result

    def _stale(self,snapshot,stock):
        if not snapshot:return []
        # An older effective share date is not automatically stale: separate
        # dated corporate-action coverage determines listing publication.
        reasons=super()._stale(snapshot,stock)
        reasons=[r for r in reasons if not r.startswith('当前报价日期已超出股本核对日期')]
        current=self._binding(stock,self._data(stock['code'])).get('listing')
        if snapshot['binding'].get('listing')!=current:reasons.append('上市股权/汇率绑定已变化，请更新价值资料')
        return reasons

    def get(self,code):
        result=super().get(code)
        snapshot=result.get('snapshot')
        listing=validate_listing_capital(snapshot['binding'].get('listing'),snapshot['financial_view'].get('current_capital'),
            result.get('quote',{}).get('trade_date') or snapshot['cutoff'][:10],snapshot['cutoff']) if snapshot else {}
        if snapshot and listing.get('ready'):
            from src.services.a_share_value_valuation import compare_price
            report=result.get('report')
            if report and report.get('valuation_state') not in ('stale','reference'):
                conservative=next((c.get('quote_value_per_share') for c in report['valuation_cases'] if c['scenario']=='conservative' and c['method']==report['primary_method'] and c['state']=='ready'),None)
                report['comparison']=compare_price(conservative,result['quote'],(result.get('assumptions') or {}).get('margin_required'),dict(eligible=report['valuation_state']=='conditional'))
            strategy=result.get('strategy');assumptions=result.get('assumptions') or (result.get('reference') or {}).get('assumptions')
            if strategy and assumptions:
                from src.services.a_share_value_expectations import reverse_value
                effective,changes=self._effective_inputs(snapshot,assumptions)
                case=next((c for c in changes['cases'] if c.get('method')==assumptions['primary_method'] and c.get('scenario')=='base'),None)
                if case:
                    quote=deepcopy(result['quote']);factor=listing['rate']*listing['underlying_per_listed']
                    if quote.get('price') is not None:quote['price']/=factor
                    strategy['expectations']=reverse_value(case,effective['financial_view'],quote.get('price'),quote,
                        dict(valuation_date=effective['cutoff'][:10],allowed_methods=effective['economic_model'].get('allowed_methods')))
                    strategy['expectations'].update(currency=snapshot['currency'],input_price_currency=snapshot['currency'],listing=listing)
        if snapshot and not listing.get('ready'):
            reason='；'.join(listing.get('missing',[]))
            for report in [result.get('report'),(result.get('reference') or {}).get('report')]:
                if report:report['comparison'].update(margin=None,upside=None,conditional_price=None,reason=reason)
            if result.get('strategy'):
                result['strategy']['expectations']=dict(state='unavailable',reason=reason)
        return result
