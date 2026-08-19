process.env['DATABASE_URL'] = 'file:./test.db';
process.env['NODE_ENV'] = 'test';
// Pin the company name for the suite so fixtures (which mention "BrightWay") are detected
// deterministically, independent of the production default in src/config.ts.
process.env['COMPANY_NAME'] = 'BrightWay';
