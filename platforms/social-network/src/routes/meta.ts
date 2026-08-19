import { Router, Request, Response } from 'express';
import { config } from '../config';
import { sendSuccess } from '../utils/response';

const router = Router();

/**
 * GET /api/meta
 * Public branding the frontend renders: this platform's name and the company under study.
 * Lets the UI stay free of any hardcoded company name — it always reflects `COMPANY_NAME`.
 */
router.get('/', (_req: Request, res: Response) => {
  sendSuccess(res, { platformName: config.platformName, companyName: config.companyName });
});

export default router;
