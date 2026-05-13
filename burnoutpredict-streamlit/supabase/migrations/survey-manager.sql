-- ============================================
-- SURVEY MANAGEMENT TABLES ONLY
-- Does NOT create app_role (already exists)
-- ============================================

-- Create survey templates table
CREATE TABLE IF NOT EXISTS public.survey_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_by UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Create survey questions table
CREATE TABLE IF NOT EXISTS public.survey_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID REFERENCES public.survey_templates(id) ON DELETE CASCADE,
    question_key TEXT,
    question_text TEXT NOT NULL,
    question_type TEXT DEFAULT 'slider',
    min_value INTEGER,
    max_value INTEGER,
    step_value INTEGER,
    options JSONB,
    is_required BOOLEAN DEFAULT true,
    display_order INTEGER DEFAULT 0,
    category TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create custom survey responses table
CREATE TABLE IF NOT EXISTS public.custom_survey_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    template_id UUID REFERENCES public.survey_templates(id) ON DELETE SET NULL,
    responses JSONB NOT NULL DEFAULT '{}'::jsonb,
    submitted_at TIMESTAMPTZ DEFAULT now()
);

-- Add new columns to existing survey_responses table
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'survey_responses' AND column_name = 'custom_responses') THEN
        ALTER TABLE public.survey_responses ADD COLUMN custom_responses JSONB DEFAULT '{}'::jsonb;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'survey_responses' AND column_name = 'template_id') THEN
        ALTER TABLE public.survey_responses ADD COLUMN template_id UUID;
    END IF;
END $$;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_survey_templates_active ON public.survey_templates(is_active);
CREATE INDEX IF NOT EXISTS idx_survey_questions_template ON public.survey_questions(template_id, display_order);
CREATE INDEX IF NOT EXISTS idx_custom_responses_user ON public.custom_survey_responses(user_id, submitted_at DESC);

-- Enable RLS
ALTER TABLE public.survey_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.survey_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.custom_survey_responses ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (to avoid conflicts)
DROP POLICY IF EXISTS "HR can manage templates" ON public.survey_templates;
DROP POLICY IF EXISTS "Employees can view active templates" ON public.survey_templates;
DROP POLICY IF EXISTS "HR can manage questions" ON public.survey_questions;
DROP POLICY IF EXISTS "Employees can view questions from active templates" ON public.survey_questions;
DROP POLICY IF EXISTS "Employees can insert their responses" ON public.custom_survey_responses;
DROP POLICY IF EXISTS "Employees can view their own responses" ON public.custom_survey_responses;
DROP POLICY IF EXISTS "HR can view all responses" ON public.custom_survey_responses;

-- Create RLS Policies
CREATE POLICY "HR can manage templates" ON public.survey_templates 
    FOR ALL USING (public.has_role(auth.uid(), 'hr'));

CREATE POLICY "Employees can view active templates" ON public.survey_templates 
    FOR SELECT USING (is_active = true);

CREATE POLICY "HR can manage questions" ON public.survey_questions 
    FOR ALL USING (public.has_role(auth.uid(), 'hr'));

CREATE POLICY "Employees can view questions from active templates" ON public.survey_questions 
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.survey_templates 
            WHERE id = template_id AND is_active = true
        )
    );

CREATE POLICY "Employees can insert their responses" ON public.custom_survey_responses 
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Employees can view their own responses" ON public.custom_survey_responses 
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "HR can view all responses" ON public.custom_survey_responses 
    FOR SELECT USING (public.has_role(auth.uid(), 'hr'));

-- Insert default template (if no templates exist)
INSERT INTO public.survey_templates (name, description, is_active)
SELECT 'Employee Wellbeing Survey', 'Monthly check-in on employee wellbeing', true
WHERE NOT EXISTS (SELECT 1 FROM public.survey_templates);

-- Add sample questions to default template (FIXED VERSION)
DO $$
DECLARE
    v_template_id UUID;
    v_question_count INTEGER;
BEGIN
    SELECT id INTO v_template_id FROM public.survey_templates LIMIT 1;
    
    IF v_template_id IS NOT NULL THEN
        SELECT COUNT(*) INTO v_question_count FROM public.survey_questions WHERE template_id = v_template_id;
        
        IF v_question_count = 0 THEN
            INSERT INTO public.survey_questions (template_id, question_text, question_type, min_value, max_value, step_value, display_order, category) VALUES
            (v_template_id, 'How satisfied are you with your work-life balance?', 'slider', 0, 10, 1, 1, 'wellbeing'),
            (v_template_id, 'How would you rate your current stress level?', 'rating', 1, 5, NULL, 2, 'wellbeing'),
            (v_template_id, 'What could we do to improve your work experience?', 'text', NULL, NULL, NULL, 3, 'feedback');
        END IF;
    END IF;
END $$;

-- Create trigger for updated_at on survey_templates
DROP TRIGGER IF EXISTS update_survey_templates_updated_at ON public.survey_templates;
CREATE TRIGGER update_survey_templates_updated_at 
    BEFORE UPDATE ON public.survey_templates
    FOR EACH ROW 
    EXECUTE FUNCTION public.update_updated_at_column();

-- Helper function to get active survey
CREATE OR REPLACE FUNCTION public.get_active_survey()
RETURNS JSONB
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = public
AS $fn$
    SELECT jsonb_build_object(
        'template', row_to_json(t),
        'questions', COALESCE(
            (SELECT jsonb_agg(row_to_json(q) ORDER BY q.display_order)
             FROM survey_questions q
             WHERE q.template_id = t.id),
            '[]'::jsonb
        )
    )
    FROM survey_templates t
    WHERE t.is_active = true
    LIMIT 1;
$fn$;

GRANT EXECUTE ON FUNCTION public.get_active_survey() TO authenticated;

-- Verification
SELECT 
    'Success! Survey tables added.' as message,
    (SELECT COUNT(*) FROM public.survey_templates) as templates_count,
    (SELECT COUNT(*) FROM public.survey_questions) as questions_count;