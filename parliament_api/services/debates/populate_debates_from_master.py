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
        
        institution = master_data.parent_institution
        lok_sabha = master_data.lok_sabha
        session = master_data.session
        is_rajya_sabha = institution and institution.name == 'rajya_sabha'
        
        # Extract PDF data from raw_api_data
        pdf_data_by_date = self._extract_pdf_urls_from_master(master_data)
        
        # ALWAYS use dates from PDF data (not available_dates) to avoid creating debates without PDFs
        # available_dates may include future dates that don't have PDFs yet
        if pdf_data_by_date:
            dates_to_process = sorted(pdf_data_by_date.keys())
            inst_name = 'RS' if is_rajya_sabha else 'LS'
            logger.info(f"{inst_name} {master_data.session_number}: Using {len(dates_to_process)} dates from PDF data (available_dates had {len(master_data.available_dates) if master_data.available_dates else 0})")
        else:
            # No PDF data available - don't create any debates
            logger.warning(f"No PDF data in master_data {master_data.id} - skipping debate creation")
            return result
        
        for date_str in dates_to_process:
            try:
                # Parse date (format: DD/MM/YYYY)
                debate_date = datetime.strptime(date_str, '%d/%m/%Y').date()
                
                # Get PDF files for this date
                pdf_files = pdf_data_by_date.get(date_str, [])
                
                if not pdf_files:
                    # Skip dates without PDFs - they shouldn't be in dates_to_process anyway
                    logger.warning(f"No PDF files found for {date_str} - skipping (this shouldn't happen)")
                    continue
                
                # Create a debate record for each PDF file (time slot)
                for idx, pdf_info in enumerate(pdf_files):
                    try:
                        pdf_url = pdf_info.get('pdf_url', '')
                        time_slot = pdf_info.get('time_slot', pdf_info.get('file_name', ''))
                        file_name = pdf_info.get('file_name', '')
                        
                        # Generate unique debate_id
                        # debate_id max_length=50, use hash of PDF URL for true uniqueness
                        if is_rajya_sabha:
                            base_id = f"rs_{master_data.session_number}_{debate_date.strftime('%Y%m%d')}"
                        else:
                            base_id = f"{master_data.lok_sabha_number}_{master_data.session_number}_{debate_date.strftime('%Y%m%d')}"
                        
                        # Add unique identifier based on PDF URL or index
                        if len(pdf_files) > 1:
                            # Multiple PDFs: use hash of PDF URL + index for true uniqueness
                            # This handles RS debates with different PDFs but same time_slot
                            unique_str = f"{pdf_url}_{idx}"
                            unique_hash = hashlib.md5(unique_str.encode()).hexdigest()[:10]
                            debate_id = f"{base_id}_{unique_hash}"
                        else:
                            # Single PDF: use category
                            debate_id = f"{base_id}_{master_data.debate_category}"
                        
                        # Ensure debate_id is under 50 chars
                        if len(debate_id) > 50:
                            # Truncate and add hash
                            truncated = debate_id[:35]
                            full_hash = hashlib.md5(debate_id.encode()).hexdigest()[:14]
                            debate_id = f"{truncated}_{full_hash}"
                        
                        # Generate metadata hash
                        metadata_hash = hashlib.sha256(
                            f"{debate_id}_{pdf_url}".encode()
                        ).hexdigest()
                        
                        # Check if debate exists
                        debate_exists = Debate.objects.filter(
                            debate_id=debate_id,
                            parent_institution=institution
                        ).exists()
                        
                        if debate_exists and not force:
                            result['skipped'] += 1
                            continue
                        
                        # Make time_slot unique by adding index if multiple debates share same title
                        # This avoids unique constraint violations
                        unique_time_slot = time_slot
                        if len(pdf_files) > 1:
                            # Add index to make time_slot unique (e.g., "Title [1]", "Title [2]")
                            unique_time_slot = f"{time_slot[:90]} [{idx}]"
                        
                        # Truncate time_slot to fit constraint (max 100 chars based on model)
                        if len(unique_time_slot) > 100:
                            unique_time_slot = unique_time_slot[:97] + "..."
                        
                        # Create or update debate record WITH PDF URL
                        debate, created = Debate.objects.update_or_create(
                            debate_id=debate_id,
                            parent_institution=institution,
                            defaults={
                                'lok_sabha': lok_sabha,
                                'session': session,
                                'debate_date': debate_date,
                                'debate_category': master_data.debate_category,
                                'debate_type': 'verbatim' if 'Verbatim' in file_name else 'text_of_debate',
                                'language': 'en',
                                'time_slot': unique_time_slot,
                                'status': 'pending',  # Always pending since we only process dates with PDFs
                                'pdf_url': pdf_url,  # NOW PROPERLY POPULATED - never empty!
                                'metadata_hash': metadata_hash,
                                'raw_api_data': {
                                    'source': 'debate_master_data',
                                    'master_data_id': master_data.id,
                                    'api_source': master_data.api_source,
                                    'file_name': file_name,
                                    'time_slot': time_slot,
                                    'original_index': idx
                                }
                            }
                        )
                        
                        if created:
                            result['created'] += 1
                            logger.debug(f"Created debate record: {debate_id} with PDF: {bool(pdf_url)}")
                        else:
                            result['updated'] += 1
                            logger.debug(f"Updated debate record: {debate_id} with PDF: {bool(pdf_url)}")
                            
                    except Exception as e:
                        logger.error(f"Error creating debate for {date_str} slot {time_slot}: {e}")
                        continue
                    
            except ValueError as e:
                logger.warning(f"Could not parse date '{date_str}': {e}")
                continue
            except Exception as e:
                logger.error(f"Error processing date '{date_str}': {e}")
                continue
        
        return result
    
    def _extract_pdf_urls_from_master(self, master_data: DebateMasterData) -> Dict[str, List[Dict]]:
        """
        Extract PDF URLs from master data's raw_api_data
        
        Returns:
            Dict mapping date strings (DD/MM/YYYY format) to lists of PDF info dicts
        """
        pdf_by_date = {}
        
        if not master_data.raw_api_data:
            return pdf_by_date
        
        institution = master_data.parent_institution
        is_rajya_sabha = institution and institution.name == 'rajya_sabha'
        
        if is_rajya_sabha:
            # RS format: all_debates_data array with pdf_url, date, time_slot
            debates_data = master_data.raw_api_data.get('all_debates_data', [])
            
            for debate in debates_data:
                raw_date = debate.get('date')
                if not raw_date:
                    continue
                
                # Convert date to DD/MM/YYYY format
                date_str = self._normalize_date_format(raw_date)
                if not date_str:
                    continue
                
                if date_str not in pdf_by_date:
                    pdf_by_date[date_str] = []
                
                # Handle pdf_url as string or array
                pdf_urls = debate.get('pdf_url', '')
                if isinstance(pdf_urls, list):
                    # Multiple PDFs for this debate entry
                    for pdf_url in pdf_urls:
                        if pdf_url:
                            pdf_by_date[date_str].append({
                                'pdf_url': pdf_url,
                                'time_slot': debate.get('time_slot', debate.get('title', '')),
                                'file_name': debate.get('file_name', debate.get('title', ''))
                            })
                elif isinstance(pdf_urls, str) and pdf_urls:
                    # Single PDF URL
                    pdf_by_date[date_str].append({
                        'pdf_url': pdf_urls,
                        'time_slot': debate.get('time_slot', debate.get('title', '')),
                        'file_name': debate.get('file_name', debate.get('title', ''))
                    })
        else:
            # LS format: dates_with_pdfs dict with fileUrl, fileName
            dates_with_pdfs = master_data.raw_api_data.get('dates_with_pdfs', {})
            for date_str, pdf_list in dates_with_pdfs.items():
                pdf_by_date[date_str] = []
                for pdf in pdf_list:
                    pdf_by_date[date_str].append({
                        'pdf_url': pdf.get('fileUrl', ''),
                        'time_slot': pdf.get('fileName', ''),
                        'file_name': pdf.get('fileName', '')
                    })
        
        return pdf_by_date
    
    def _normalize_date_format(self, date_str: str) -> str:
        """
        Normalize date to DD/MM/YYYY format from various inputs
        
        Args:
            date_str: Date in various formats (DD/MM/YYYY, YYYY-MM-DD, etc.)
            
        Returns:
            Date in DD/MM/YYYY format or empty string if invalid
        """
        if not date_str:
            return ''
        
        try:
            # Try DD/MM/YYYY format
            if '/' in date_str:
                parts = date_str.split('/')
                if len(parts) == 3:
                    if len(parts[2]) == 4:  # DD/MM/YYYY
                        return date_str
                    elif len(parts[0]) == 4:  # YYYY/MM/DD
                        return f"{parts[2]}/{parts[1]}/{parts[0]}"
            
            # Try YYYY-MM-DD format
            if '-' in date_str:
                parts = date_str.split('-')
                if len(parts) == 3 and len(parts[0]) == 4:
                    year, month, day = parts
                    return f"{day}/{month}/{year}"
            
            # Try to parse with datetime
            for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y']:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime('%d/%m/%Y')
                except ValueError:
                    continue
            
            logger.warning(f"Could not normalize date format: {date_str}")
            return ''
            
        except Exception as e:
            logger.warning(f"Error normalizing date '{date_str}': {e}")
            return ''
    
    def _normalize_time_slot(self, time_slot: str, index: int) -> str:
        """
        Normalize time slot string for use in debate_id
        
        Args:
            time_slot: Time slot string (e.g., "11:00-12:00 Noon", "Full Day")
            index: Index if time slot is empty
            
        Returns:
            Normalized string safe for use in ID
        """
        if not time_slot:
            return f"slot{index}"
        
        # Replace problematic characters
        normalized = time_slot.lower()
        normalized = normalized.replace(':', '')
        normalized = normalized.replace('-', 'to')
        normalized = normalized.replace(' ', '_')
        normalized = normalized.replace('/', '_')
        normalized = normalized.replace('(', '')
        normalized = normalized.replace(')', '')
        
        # Shorten common patterns
        normalized = normalized.replace('full_day', 'fullday')
        normalized = normalized.replace('noon', 'n')
        normalized = normalized.replace('_pm', 'pm')
        normalized = normalized.replace('_am', 'am')
        
        return normalized[:50]  # Limit length
    
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
