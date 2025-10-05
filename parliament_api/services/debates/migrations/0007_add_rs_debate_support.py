# Generated manually for RS debates support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('debates', '0005_add_parliament_institution_support'),
    ]

    operations = [
        # Add time_slot field
        migrations.AddField(
            model_name='debate',
            name='time_slot',
            field=models.CharField(blank=True, help_text='Time slot for RS verbatim debates (e.g., "11:00-12:00 Noon") or Question number for RS official debates', max_length=100, null=True),
        ),
        # Update debate_category choices (this is handled by model, but document it)
        migrations.AlterField(
            model_name='debate',
            name='debate_category',
            field=models.CharField(choices=[('uncorrected', 'Uncorrected Proceedings'), ('corrected', 'Corrected Proceedings'), ('synopsis', 'Synopsis'), ('text_of_debate', 'Text of Debate'), ('verbatim', 'Verbatim Debates (RS)'), ('official_qa', 'Official Q&A (RS)'), ('official_other', 'Official Other (RS)'), ('official', 'Official Debates (RS)')], default='uncorrected', help_text='Whether this is corrected or uncorrected proceedings', max_length=20),
        ),
        # Update unique_together constraint
        migrations.AlterUniqueTogether(
            name='debate',
            unique_together={('parent_institution', 'debate_date', 'debate_category', 'language', 'time_slot')},
        ),
        # Add index for time_slot
        migrations.AddIndex(
            model_name='debate',
            index=models.Index(fields=['time_slot'], name='debates_deb_time_sl_idx'),
        ),
    ]
