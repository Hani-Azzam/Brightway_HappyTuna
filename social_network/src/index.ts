import { config } from './config';
import { createApp } from './server';
import { logger } from './utils/logger';

const app = createApp();

app.listen(config.port, () => {
  logger.info({ port: config.port }, 'BrightWay platform server started');
});
