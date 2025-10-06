"""
Service to populate individual Debate records from DebateMasterData
Creates queryable records for each debate day from session-level metadata
"""
import logging
from datetime import datetime
from django.db import transaction
from django.utils import timezone
from typing import Dict, List
import hashlib

from .models import DebateMasterData, Debate
from services.questions.models import ParliamentInstitution

logger = logging.getLogger(__name__)


class DebatePopulationService:
    """
    Populate individual Debate records from DebateMasterData
    
    This creates queryable database records for each debate day,
    making them visible in the Data Explorer before PDFs are downloaded.
    """
    
    def populate_debates_from_master_data(
        self, 
        force: bool = False,
        institution: str = None,
        lok_sabha: str = None,
        session: str = None
    ) -> Dict:
        """
        Populate Debate records from DebateMasterData
        
        Args:
            force: If True, recreate even if debates exist
            institution: Filter by institution (lok_sabha or rajya_sabha)
            lok_sabha: Filter by specific Lok Sabha number
            session: Filter by specific session number
            
        Returns:
            Dict with statistics about the population process
        """
        logger.info("🚀 Starting debate population from master data...")
        
        # Build queryset
        queryset = DebateMasterData.objects.all()
        
        if institution:
            inst_obj = ParliamentInstitution.objects.get(name=institution)
            queryset = queryset.filter(parent_institution=inst_obj)
        
        if lok_sabha:
            queryset = queryset.filter(lok_sabha_number=lok_sabha)
        
        if session:
            queryset = queryset.filter(session_number=session)
        
        total_master_records = queryset.count()
        logger.info(f"Found {total_master_records} master data records to process")
        
        stats = {
            'master_records_processed': 0,
            'debates_created': 0,
            'debates_updated': 0,
            'debates_skipped': 0,
            'errors': []
        }
        
        for master_data in queryset:
            try:
                result = self._populate_debates_for_session(master_data, force)
                stats['master_records_processed'] += 1
                stats['debates_created'] += result['created']
                stats['debates_updated'] += result['updated']
                stats['debates_skipped'] += result['skipped']
                
            except Exception as e:
                error_msg = f"Error processing {master_data}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                stats['errors'].append(error_msg)
        
        logger.info(f"✅ Population complete: {stats['debates_created']} created, {stats['debates_updated']} updated")
        
        return {
            'status': 'SUCCESS' if not stats['errors'] else 'PARTIAL_SUCCESS',
            'statistics': stats
        }
    
    def _populate_debates_for_session(self, master_data: DebateMasterData, force: bool) -> Dict:
        """
        Populate Debate records for a single session from its master data
        
        Args:
            master_data: DebateMasterData instance
            force: If True, update existing records
            
        Returns:
            Dict with created, updated, skipped counts
        """
        result = {'created': 0, 'updated': 0, 'skipped': 0}
        
        if not master_data.available_dates:
            logger.warning(f"No available dates in {master_data}")
            return result
        
        institution = master_data.parent_institution
        lok_sabha = master_data.lok_sabha
        session = master_data.session
        
        for date_str in master_data.available_dates:
            try:
                # Parse date (format: DD/MM/YYYY)
                debate_date = datetime.strptime(date_str, '%d/%m/%Y').date()
                
                # Generate unique debate_id
                if institution and institution.name == 'rajya_sabha':
                    debate_id = f"rs_{master_data.session_number}_{debate_date.strftime('%Y%m%d')}_{master_data.debate_category}"
                else:
                    debate_id = f"{master_data.lok_sabha_number}_{master_data.session_number}_{debate_date.strftime('%Y%m%d')}_{master_data.debate_category}"
                
                # Generate metadata hash
                metadata_hash = hashlib.sha256(
                    f"{debate_id}_{master_data.debate_category}".encode()
                ).hexdigest()
                
                # Check if debate exists
                debate_exists = Debate.objects.filter(
                    debate_id=debate_id,
                    parent_institution=institution
                ).exists()
                
                if debate_exists and not force:
                    result['skipped'] += 1
                    continue
                
                # Create or update debate record
                debate, created = Debate.objects.update_or_create(
                    debate_id=debate_id,
                    parent_institution=institution,
                    defaults={
                        'lok_sabha': lok_sabha,
                        'session': session,
                        'debate_date': debate_date,
                        'debate_category': master_data.debate_category,
                        'debate_type': 'text_of_debate',
                        'language': 'en',  # Default, will be updated by scraper
                        'status': 'pending',  # Ready for download
                        'pdf_url': '',  # Will be populated by scraper
                        'metadata_hash': metadata_hash,
                        'raw_api_data': {
                            'source': 'debate_master_data',
                            'master_data_id': master_data.id,
                            'api_source': master_data.api_source
                        }
                    }
                )
                
                if created:
                    result['created'] += 1
                    logger.debug(f"Created debate record: {debate_id}")
                else:
                    result['updated'] += 1
                    logger.debug(f"Updated debate record: {debate_id}")
                    
            except ValueError as e:
                logger.warning(f"Could not parse date '{date_str}': {e}")
                continue
            except Exception as e:
                logger.error(f"Error creating debate for date '{date_str}': {e}")
                continue
        
        return result
    
    def get_population_status(self) -> Dict:
        """
        Get status of debate population
        
        Returns:
            Dict with statistics about populated vs available debates
        """
        ls_inst = ParliamentInstitution.objects.get(name='lok_sabha')
        rs_inst = ParliamentInstitution.objects.get(name='rajya_sabha')
        
        # Count master data dates
        ls_master = DebateMasterData.objects.filter(parent_institution=ls_inst)
        rs_master = DebateMasterData.objects.filter(parent_institution=rs_inst)
        
        ls_total_dates = sum([len(m.available_dates) for m in ls_master])
        rs_total_dates = sum([len(m.available_dates) for m in rs_master])
        
        # Count actual debate records
        ls_debates = Debate.objects.filter(parent_institution=ls_inst).count()
        rs_debates = Debate.objects.filter(parent_institution=rs_inst).count()
        
        return {
            'lok_sabha': {
                'master_sessions': ls_master.count(),
                'available_dates': ls_total_dates,
                'debate_records': ls_debates,
                'population_percentage': round((ls_debates / ls_total_dates * 100), 2) if ls_total_dates > 0 else 0
            },
            'rajya_sabha': {
                'master_sessions': rs_master.count(),
                'available_dates': rs_total_dates,
                'debate_records': rs_debates,
                'population_percentage': round((rs_debates / rs_total_dates * 100), 2) if rs_total_dates > 0 else 0
            }
        }
