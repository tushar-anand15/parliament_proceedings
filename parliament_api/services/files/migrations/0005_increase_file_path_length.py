# Generated manually to fix varchar(100) constraint on file_path

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0004_alter_documentfile_document_category_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentfile',
            name='file_path',
            field=models.FileField(blank=True, max_length=500, null=True, upload_to='pdfs/'),
        ),
    ]

