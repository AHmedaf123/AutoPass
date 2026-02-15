import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

async def get_job():
    engine = create_async_engine('postgresql+asyncpg://admin:postgres@localhost:5432/jobapplier')
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        result = await session.execute(
            text("SELECT id, title, company, description FROM job_listings WHERE id = 'a99aac04-a892-44a0-9076-9538ed5ffa38'")
        )
        row = result.fetchone()
        if row:
            print('JOB ID:', row[0])
            print('TITLE:', row[1])
            print('COMPANY:', row[2])
            print('DESCRIPTION:')
            print(row[3][:3000] if row[3] else 'No description')
        else:
            print('Job not found')

asyncio.run(get_job())
