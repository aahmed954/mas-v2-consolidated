from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(host='localhost', port=6333)

# Your leather business collections mapped from the scan
COLLECTIONS = {
    'work-buddy-leather-business': 'Core leather operations (14,775 docs)',
    'work-buddy-import-export': 'International trade (6,587 docs)',
    'work-buddy-finance-tax': 'Financial records (11,470 docs)',
    'work-buddy-legal-estate': 'Legal matters (1,573 docs)',
    'work-buddy-correspondence': 'Communications (42 docs)',
    'work-buddy-general': 'Miscellaneous (113 docs)'
}

print('🚀 Creating YOUR business collections...')
created = 0
existing = 0

for name, desc in COLLECTIONS.items():
    try:
        client.get_collection(name)
        print(f'  ✓ {name} already exists')
        existing += 1
    except:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            optimizers_config={
                "default_segment_number": 2,
                "indexing_threshold": 20000,
            }
        )
        print(f'  ✅ Created {name} - {desc}')
        created += 1

print(f'\n✨ Status: {created} new, {existing} existing')
print('\n📊 Your complete RAG architecture:')

all_collections = client.get_collections().collections
for col in all_collections:
    if 'work-buddy' in col.name:
        info = client.get_collection(col.name)
        print(f'  {col.name}: {info.points_count} vectors')

print('\n🎯 Ready for ingestion!')
print('   34,562 documents categorized and ready')
print('   Your leather business is about to become instantly searchable!')
