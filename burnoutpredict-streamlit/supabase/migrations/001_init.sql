-- BurnoutPredict — full schema for the Streamlit edition.
-- Run this once in your Supabase SQL editor on a fresh project.
-- (Identical to the original ThriveWell AI / BurnoutPredict schema.)

CREATE TYPE public.app_role AS ENUM ('hr', 'employee');

CREATE TABLE public.profiles (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name    TEXT NOT NULL,
  department   TEXT,
  job_title    TEXT,
  employee_code TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.user_roles (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role       public.app_role NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, role)
);

CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role public.app_role)
RETURNS BOOLEAN LANGUAGE SQL STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role = _role)
$fn$;

CREATE TABLE public.survey_responses (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                  UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  emotional_exhaustion     INT NOT NULL CHECK (emotional_exhaustion BETWEEN 0 AND 6),
  depersonalization        INT NOT NULL CHECK (depersonalization BETWEEN 0 AND 6),
  personal_accomplishment  INT NOT NULL CHECK (personal_accomplishment BETWEEN 0 AND 6),
  workload                 INT NOT NULL CHECK (workload BETWEEN 0 AND 6),
  support                  INT NOT NULL CHECK (support BETWEEN 0 AND 6),
  sleep_hours              NUMERIC(3,1) NOT NULL,
  work_hours               NUMERIC(4,1) NOT NULL,
  notes                    TEXT,
  ai_sentiment             TEXT,
  ai_urgency               TEXT,
  ai_summary               TEXT,
  ai_themes                JSONB DEFAULT '[]'::jsonb,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.risk_scores (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  survey_id       UUID REFERENCES public.survey_responses(id) ON DELETE SET NULL,
  burnout_score   NUMERIC(5,2) NOT NULL,
  risk_level      TEXT NOT NULL CHECK (risk_level IN ('low','moderate','high')),
  top_factors     JSONB NOT NULL DEFAULT '[]'::jsonb,
  recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.attrition_predictions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL,
  probability NUMERIC NOT NULL,
  risk_band   TEXT NOT NULL,
  drivers     JSONB NOT NULL DEFAULT '[]'::jsonb,
  features    JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_risk_scores_user ON public.risk_scores(user_id, created_at DESC);
CREATE INDEX idx_surveys_user      ON public.survey_responses(user_id, created_at DESC);
CREATE INDEX idx_attrition_user    ON public.attrition_predictions(user_id, created_at DESC);

CREATE OR REPLACE FUNCTION public.update_updated_at_column() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = public AS $fn$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $fn$;

CREATE TRIGGER update_profiles_updated_at BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE OR REPLACE FUNCTION public.handle_new_user() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
DECLARE _role public.app_role;
BEGIN
  INSERT INTO public.profiles (user_id, full_name, department, job_title, employee_code)
  VALUES (NEW.id,
          COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email,'@',1)),
          NEW.raw_user_meta_data->>'department',
          NEW.raw_user_meta_data->>'job_title',
          NEW.raw_user_meta_data->>'employee_code');
  _role := COALESCE((NEW.raw_user_meta_data->>'role')::public.app_role, 'employee');
  INSERT INTO public.user_roles (user_id, role) VALUES (NEW.id, _role);
  RETURN NEW;
END; $fn$;

CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

ALTER TABLE public.profiles              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_roles            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.survey_responses      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_scores           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.attrition_predictions ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_view_own_profile     ON public.profiles      FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY p_hr_view_all_profiles ON public.profiles      FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'hr'));
CREATE POLICY p_update_own_profile   ON public.profiles      FOR UPDATE TO authenticated USING (auth.uid() = user_id);
CREATE POLICY r_view_own_role        ON public.user_roles    FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY r_hr_view_all_roles    ON public.user_roles    FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'hr'));
CREATE POLICY s_insert_own           ON public.survey_responses FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY s_view_own             ON public.survey_responses FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY s_update_own           ON public.survey_responses FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY s_hr_view_all          ON public.survey_responses FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'hr'));
CREATE POLICY rs_view_own            ON public.risk_scores   FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY rs_hr_view_all         ON public.risk_scores   FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'hr'));
CREATE POLICY rs_insert_own          ON public.risk_scores   FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY ap_view_own            ON public.attrition_predictions FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY ap_hr_view_all         ON public.attrition_predictions FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'hr'));
CREATE POLICY ap_hr_insert           ON public.attrition_predictions FOR INSERT TO authenticated WITH CHECK (public.has_role(auth.uid(), 'hr'));
