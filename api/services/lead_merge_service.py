# api/services/lead_merge_service.py
import logging
from django.db import transaction, models
from ..models import Lead, LeadNote, LeadEvent, SearchRunLead, PeopleSearch, LeadDuplicate
from ..repositories.lead_repository import LeadRepository
from django.db.models import Q # Import Q object for complex lookups

logger = logging.getLogger(__name__)

class LeadMergeService:
    @staticmethod
    def _get_lead(lead_id):
        lead = Lead.objects.filter(third_party_org_id=str(lead_id)).first()
        return lead

    @classmethod
    def merge_leads(cls, source_lead_id: str, target_lead_id: str, org_id: str = None):
        """
        Merges a source lead into a target lead.
        All related objects from the source lead are reassigned to the target lead.
        The source lead is then deleted.
        """
        if source_lead_id == target_lead_id:
            raise ValueError("Source and target lead IDs cannot be the same.")

        with transaction.atomic():
            source_lead = cls._get_lead(source_lead_id)
            target_lead = cls._get_lead(target_lead_id)

            if not source_lead:
                raise Lead.DoesNotExist(f"Source lead with ID {source_lead_id} not found.")
            if not target_lead:
                raise Lead.DoesNotExist(f"Target lead with ID {target_lead_id} not found.")

            logger.info(f"Merging lead {source_lead.id} into {target_lead.id}")

            # 1. Reassign related objects from source to target
            # LeadNotes
            LeadNote.objects.filter(lead=source_lead).update(lead=target_lead)
            logger.debug(f"Reassigned notes from {source_lead.id} to {target_lead.id}")

            # LeadEvents
            LeadEvent.objects.filter(lead=source_lead).update(lead=target_lead)
            logger.debug(f"Reassigned events from {source_lead.id} to {target_lead.id}")

            # SearchRunLead (many-to-many through model)
            # Ensure no duplicates in SearchRunLead relationship
            for srl in SearchRunLead.objects.filter(lead=source_lead):
                if not SearchRunLead.objects.filter(search_run=srl.search_run, lead=target_lead).exists():
                    srl.lead = target_lead
                    srl.save()
                else:
                    srl.delete() # If already exists, delete the redundant entry
            logger.debug(f"Reassigned SearchRunLead relationships from {source_lead.id} to {target_lead.id}")

            # PeopleSearch (many-to-many through default manager)
            for ps in PeopleSearch.objects.filter(leads=source_lead):
                ps.leads.remove(source_lead)
                ps.leads.add(target_lead)
            logger.debug(f"Reassigned PeopleSearch relationships from {source_lead.id} to {target_lead.id}")


            # 2. Consolidate Lead Data (prioritize target, then source if target is null/empty)
            for field in source_lead._meta.fields:
                field_name = field.name
                if field_name in ['id', 'created_at', 'updated_at', 'third_party_org_id']: # Skip primary keys and timestamps
                    continue

                source_value = getattr(source_lead, field_name)
                target_value = getattr(target_lead, field_name)

                # Special handling for JSONFields (like tags_json, other_social_urls)
                if isinstance(field, models.JSONField):
                    if field_name == 'tags_json':
                        # Combine lists, remove duplicates
                        combined_tags = list(set((target_value or []) + (source_value or [])))
                        setattr(target_lead, field_name, combined_tags)
                    elif field_name == 'other_social_urls':
                        # Merge dictionaries
                        merged_social_urls = (target_value or {})
                        merged_social_urls.update(source_value or {})
                        setattr(target_lead, field_name, merged_social_urls)
                    elif field_name == 'source_meta' or field_name == 'score_components':
                        # Merge dictionaries, potentially overriding with source values (source takes precedence if conflicting)
                        merged_json = (target_value or {})
                        merged_json.update(source_value or {})
                        setattr(target_lead, field_name, merged_json)
                    else:
                        # For other JSON fields, if target is empty, use source
                        if not target_value and source_value:
                            setattr(target_lead, field_name, source_value)
                else:
                    # For non-JSON fields, if target is empty/None, use source value
                    if target_value is None or target_value == '' or (isinstance(target_value, (list, dict)) and not target_value):
                        if source_value is not None and source_value != '':
                            setattr(target_lead, field_name, source_value)

            target_lead.save()
            logger.debug(f"Consolidated data from {source_lead.id} to {target_lead.id}")


            # 3. Update Deduplication Relationships
            # If source_lead was a primary lead for other duplicates, update them to point to target_lead
            # Use third_party_org_id for external references, but internal ID might also be used
            # Also update dedupe_group_id if the primary lead is changing
            Lead.objects.filter(Q(primary_lead_id=source_lead.third_party_org_id) | Q(primary_lead_id=str(source_lead.id))).update(
                primary_lead_id=target_lead.third_party_org_id or str(target_lead.id),
                dedupe_group_id=target_lead.dedupe_group_id or source_lead.dedupe_group_id
            )

            # If source_lead was part of a dedupe group, ensure target_lead is now the primary if needed
            # Or simply ensure target_lead gets the dedupe_group_id if it didn't have one
            if source_lead.dedupe_group_id and not target_lead.dedupe_group_id:
                target_lead.dedupe_group_id = source_lead.dedupe_group_id
                # If target was 'original', it now becomes 'primary' of this group
                if target_lead.dedupe_state == 'original' or not target_lead.dedupe_state:
                    target_lead.dedupe_state = 'primary'
                target_lead.save(update_fields=['dedupe_group_id', 'dedupe_state', 'updated_at'])
            
            # If target was 'original' and source was 'primary', update target state
            elif target_lead.dedupe_state == 'original' and source_lead.dedupe_state == 'primary':
                target_lead.dedupe_state = 'primary'
                target_lead.save(update_fields=['dedupe_state', 'updated_at'])
            
            # Update LeadDuplicate entries where source_lead was the original_lead
            LeadDuplicate.objects.filter(original_lead=source_lead).update(original_lead=target_lead)
            # Update LeadDuplicate entries where source_lead was the duplicate_lead
            LeadDuplicate.objects.filter(duplicate_lead=source_lead).update(duplicate_lead=target_lead)


            # 4. Delete the source lead
            source_lead_id_val = source_lead.id # Store for logging before deletion
            source_lead.delete()
            logger.info(f"Source lead {source_lead_id_val} deleted successfully.")

            # 5. Log the merge event on the target lead
            LeadRepository.create_lead_event(
                lead=target_lead,
                event_type="lead_merged",
                org_id=org_id, # Requires org_id to be passed
                metadata={"merged_from_lead_id": str(source_lead_id_val)}
            )

        return target_lead
