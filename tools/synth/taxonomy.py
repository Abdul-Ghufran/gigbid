"""Skill taxonomy used by the synthetic-world generator.

Each skill has:
  domain   - ai | web | data | general
  syn      - common synonyms; these are ALSO exported to GigBid's own skill normaliser
  hard     - paraphrases used only by the generator (the system never sees this list), so
             retrieval has to cope with skills that are implied rather than named
  imports  - code tokens that imply the skill inside source files
"""

SKILLS: dict[str, dict] = {
    # ---------------- general ----------------
    "Python": {"domain": "general", "syn": ["python3"], "hard": ["a Python codebase"], "imports": ["import os", "def main("]},
    "Docker": {"domain": "general", "syn": ["containers", "docker-compose"], "hard": ["containerised the stack", "shipped it as an image"], "imports": ["FROM python:", "FROM node:"]},
    "AWS": {"domain": "general", "syn": ["amazon web services", "s3", "ec2", "lambda"], "hard": ["Amazon's cloud", "serverless functions on Amazon"], "imports": ["import boto3"]},
    "CI/CD": {"domain": "general", "syn": ["github actions", "continuous integration"], "hard": ["automated build-and-deploy pipeline"], "imports": ["runs-on: ubuntu-latest"]},
    # ---------------- ai ----------------
    "PyTorch": {"domain": "ai", "syn": ["torch"], "hard": ["a deep-learning framework from Meta"], "imports": ["import torch", "from torch import nn"]},
    "scikit-learn": {"domain": "ai", "syn": ["sklearn"], "hard": ["classical ML toolkit"], "imports": ["from sklearn.ensemble import RandomForestClassifier"]},
    "XGBoost": {"domain": "ai", "syn": ["gradient boosting", "lightgbm"], "hard": ["boosted trees"], "imports": ["import xgboost"]},
    "LangChain": {"domain": "ai", "syn": ["langgraph", "llm orchestration"], "hard": ["chained LLM calls"], "imports": ["from langchain_core.prompts import ChatPromptTemplate"]},
    "RAG": {"domain": "ai", "syn": ["retrieval-augmented generation", "retrieval augmented generation"], "hard": ["answers grounded in the client's own documents", "document Q&A bot"], "imports": ["def retrieve("]},
    "LLM fine-tuning": {"domain": "ai", "syn": ["fine-tuning", "lora", "qlora"], "hard": ["adapted an open model to their tone"], "imports": ["from peft import LoraConfig"]},
    "Hugging Face": {"domain": "ai", "syn": ["transformers", "huggingface"], "hard": ["pretrained models from the Hub"], "imports": ["from transformers import AutoModel"]},
    "Computer vision": {"domain": "ai", "syn": ["opencv", "image classification", "object detection"], "hard": ["read defects off camera frames", "spotted items in photos"], "imports": ["import cv2"]},
    "NLP": {"domain": "ai", "syn": ["natural language processing", "text classification", "spacy"], "hard": ["made sense of free-text tickets"], "imports": ["import spacy"]},
    "Pinecone": {"domain": "ai", "syn": ["vector database"], "hard": ["a managed vector index"], "imports": ["from pinecone import Pinecone"]},
    "FAISS": {"domain": "ai", "syn": ["similarity search"], "hard": ["nearest-neighbour lookups"], "imports": ["import faiss"]},
    "MLflow": {"domain": "ai", "syn": ["experiment tracking", "model registry"], "hard": ["kept every run reproducible and comparable"], "imports": ["import mlflow"]},
    "Time-series forecasting": {"domain": "ai", "syn": ["forecasting", "prophet", "arima"], "hard": ["predicted next month's demand"], "imports": ["from prophet import Prophet"]},
    "Recommendation systems": {"domain": "ai", "syn": ["recommender", "collaborative filtering"], "hard": ["suggested what each shopper should see next"], "imports": ["from implicit.als import AlternatingLeastSquares"]},
    "FastAPI": {"domain": "ai", "syn": ["fastapi backend"], "hard": ["a typed Python web API"], "imports": ["from fastapi import FastAPI"]},
    "MLOps": {"domain": "ai", "syn": ["model deployment", "model monitoring"], "hard": ["kept the model healthy in production"], "imports": ["from evidently.report import Report"]},
    # ---------------- web ----------------
    "React": {"domain": "web", "syn": ["reactjs", "react.js"], "hard": ["component-based front end"], "imports": ["import React", "import { useState } from 'react'"]},
    "Next.js": {"domain": "web", "syn": ["nextjs", "next"], "hard": ["server-rendered React"], "imports": ["import Link from 'next/link'"]},
    "TypeScript": {"domain": "web", "syn": ["ts"], "hard": ["strictly typed JavaScript"], "imports": ["interface Props", ": string"]},
    "Node.js": {"domain": "web", "syn": ["nodejs", "express"], "hard": ["a JavaScript server"], "imports": ["require('express')", "import express from 'express'"]},
    "Django": {"domain": "web", "syn": ["django rest framework", "drf"], "hard": ["batteries-included Python web framework"], "imports": ["from django.db import models"]},
    "PostgreSQL": {"domain": "web", "syn": ["postgres", "psql"], "hard": ["a relational database"], "imports": ["import psycopg", "postgresql://"]},
    "Redis": {"domain": "web", "syn": ["caching layer"], "hard": ["in-memory cache"], "imports": ["import redis", "new Redis("]},
    "Celery": {"domain": "web", "syn": ["task queue"], "hard": ["background jobs that run off the request path", "queue workers"], "imports": ["from celery import Celery"]},
    "GraphQL": {"domain": "web", "syn": ["apollo"], "hard": ["one flexible query endpoint"], "imports": ["gql`", "import { buildSchema } from 'graphql'"]},
    "Tailwind CSS": {"domain": "web", "syn": ["tailwind"], "hard": ["utility-first styling"], "imports": ["@tailwind base"]},
    "Stripe": {"domain": "web", "syn": ["payments integration", "stripe checkout"], "hard": ["took card payments and subscriptions"], "imports": ["import Stripe", "stripe.checkout"]},
    "WebSockets": {"domain": "web", "syn": ["socket.io", "real-time"], "hard": ["live updates pushed to the browser"], "imports": ["new WebSocket(", "socket.io"]},
    "MongoDB": {"domain": "web", "syn": ["mongo", "mongoose"], "hard": ["a document store"], "imports": ["mongoose.connect"]},
    "Playwright": {"domain": "web", "syn": ["e2e testing", "end-to-end tests"], "hard": ["browser tests that click through the flows"], "imports": ["import { test, expect } from '@playwright/test'"]},
    "Shopify": {"domain": "web", "syn": ["shopify app", "liquid"], "hard": ["an online-store platform plugin"], "imports": ["import { shopifyApi } from '@shopify/shopify-api'"]},
    # ---------------- data ----------------
    "SQL": {"domain": "data", "syn": ["sql queries", "window functions"], "hard": ["wrote the queries behind every number"], "imports": ["SELECT ", "GROUP BY"]},
    "Excel": {"domain": "data", "syn": ["spreadsheets", "pivot tables", "vlookup"], "hard": ["a workbook the finance team lives in"], "imports": ["import openpyxl"]},
    "Power BI": {"domain": "data", "syn": ["powerbi", "dax"], "hard": ["Microsoft's BI dashboards"], "imports": ["CALCULATE("]},
    "Tableau": {"domain": "data", "syn": ["tableau dashboards"], "hard": ["drag-and-drop visual analytics"], "imports": ["import tableauserverclient"]},
    "dbt": {"domain": "data", "syn": ["data build tool", "dbt models"], "hard": ["version-controlled SQL transformations"], "imports": ["{{ ref("]},
    "pandas": {"domain": "data", "syn": ["dataframes"], "hard": ["cleaned the data in notebooks"], "imports": ["import pandas as pd"]},
    "Looker": {"domain": "data", "syn": ["lookml", "looker studio"], "hard": ["Google's semantic-layer BI"], "imports": ["explore:"]},
    "Google Analytics": {"domain": "data", "syn": ["ga4", "web analytics"], "hard": ["traffic and funnel tracking for the site"], "imports": ["gtag("]},
    "BigQuery": {"domain": "data", "syn": ["bigquery warehouse"], "hard": ["Google's serverless warehouse"], "imports": ["from google.cloud import bigquery"]},
    "Snowflake": {"domain": "data", "syn": ["snowflake warehouse"], "hard": ["a cloud data warehouse"], "imports": ["import snowflake.connector"]},
    "Airflow": {"domain": "data", "syn": ["dag scheduling", "orchestration"], "hard": ["scheduled nightly pipelines"], "imports": ["from airflow import DAG"]},
    "Statistics": {"domain": "data", "syn": ["hypothesis testing", "regression analysis"], "hard": ["checked whether the difference was real"], "imports": ["from scipy import stats"]},
    "A/B testing": {"domain": "data", "syn": ["experimentation", "split testing"], "hard": ["compared two versions of the page on live traffic"], "imports": ["def ab_test("]},
    "Data visualization": {"domain": "data", "syn": ["dashboards", "charts", "matplotlib"], "hard": ["turned the numbers into pictures executives read"], "imports": ["import matplotlib.pyplot as plt"]},
    "ETL": {"domain": "data", "syn": ["data pipelines", "elt"], "hard": ["moved data from the CRM into one place every night"], "imports": ["def extract("]},
}

DOMAIN_SKILLS = {d: [s for s, v in SKILLS.items() if v["domain"] in (d, "general")] for d in ("ai", "web", "data")}

GENERIC_OPENINGS = [
    "Dear Sir/Madam, I have read your job post carefully and I am very interested.",
    "Hello, I am a passionate and hardworking professional with many years of experience.",
    "Hi there! I am the perfect fit for this job and can start immediately.",
    "Greetings! I have gone through your requirements and I can do this job.",
]
