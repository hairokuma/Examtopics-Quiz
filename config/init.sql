-- id	3
-- name	DP-700 Fabric Data Engineer Associate
-- description	Microsoft Fabric Data Engineer Associate Exam
-- questions	118
-- link	https://examtopics.com/exams/microsoft/dp-700/view/
-- created_at	2026-01-12 11:43:37
-- updated_at	2026-01-12 11:43:37

-- Microsoft AI-100 Azure AI Engineer Associate 
-- Designing and Implementing an Azure AI Solution

-- Microsoft AI -900 Azure AI Fundamentals
-- Demonstrate fundamental AI concepts related to the development of software and services of Microsoft Azure to create AI solutions.

-- Microsoft Certified: Azure Administrator Associate
-- Demonstrate key skills to configure, manage, secure, and administer key professional functions in Microsoft Azure.
-- Microsoft AZ-104 Actual Exam Questions Last updated on Jan. 5, 2026. questions 606


INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        7,
        'Microsoft AI-900 Azure AI Fundamentals',
        'Demonstrate fundamental AI concepts related to the development of software and services of Microsoft Azure to create AI solutions.',
        246,
        'https://examtopics.com/exams/microsoft/ai-102/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2025-12-24'
    );

-- Microsoft Certified: Azure Administrator Associate
-- Demonstrate key skills to configure, manage, secure, and administer key professional functions in Microsoft Azure.
-- Microsoft AZ-104 Actual Exam Questions Last updated on Jan. 5, 2026. questions 606
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        8,
        'Microsoft Certified: Azure Administrator Associate',
        'Demonstrate key skills to configure, manage, secure, and administer key professional functions in Microsoft Azure.',
        606,
        'https://examtopics.com/exams/microsoft/az-104/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-05'
    );


-- Microsoft AZ-302 Azure Solutions Architect
-- Designing Microsoft Azure Infrastructure Solutions
-- Last updated on Dec. 22, 2025. questions 55
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        9,
        'Microsoft AZ-302 Azure Solutions Architect',
        'Designing Microsoft Azure Infrastructure Solutions',
        55,
        'https://examtopics.com/exams/microsoft/az-302/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2025-12-22'
    );


-- get questions where /assets/ is in the content bunt not https://www.examtopics.com/assets (question_text, answer_object or correct_answer_text)
SELECT * FROM questions_scraped WHERE question_text LIKE '%/assets/%' AND question_text NOT LIKE '%https://www.examtopics.com/assets/%'
   OR answer_object LIKE '%/assets/%' AND answer_object NOT LIKE '%https://www.examtopics.com/assets/%'
   OR correct_answer_text LIKE '%/assets/%' AND correct_answer_text NOT LIKE '%https://www.examtopics.com/assets/%';



  --  select question_scraped where correct_answer_key is null or [] 
SELECT * FROM questions_scraped WHERE correct_answer_keys IS NULL OR correct_answer_keys = '[]';


-- Microsoft AZ-400 Azure DevOps Engineer Expert
-- Last updated on Jan. 13, 2026. questions 564
-- As a DevOps engineer, you design and implement strategies for collaboration, code, infrastructure, source control, security, compliance, continuous integration, testing, delivery, monitoring, and feedback.
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        10,
        'Microsoft AZ-400 Azure DevOps Engineer Expert',
        'As a DevOps engineer, you design and implement strategies for collaboration, code, infrastructure, source control, security, compliance, continuous integration, testing, delivery, monitoring, and feedback.',
        564,
        'https://examtopics.com/exams/microsoft/az-400/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-13'
    );

    -- Microsoft AZ-500 Azure Security Engineer Associate
    -- Last updated on Jan. 13, 2026. questions 505
    -- As an Azure Security Engineer, you implement security controls and threat protection, manage identity and access, and protect data, applications, and networks in cloud and hybrid environments as part of an end-to-end infrastructure.
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        11,
        'Microsoft AZ-500 Azure Security Engineer Associate',
        'As an Azure Security Engineer, you implement security controls and threat protection, manage identity and access, and protect data, applications, and networks in cloud and hybrid environments as part of an end-to-end infrastructure.',
        505,
        'https://examtopics.com/exams/microsoft/az-500/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-13'
    );


    -- Microsoft AZ-700 Azure Network Engineer Associate
    -- Last updated on Jan. 7, 2026. questions 369
    -- As an Azure Network Engineer, you plan, implement, and maintain Azure networking solutions, including hybrid networking, connectivity, routing, security, and private access to Azure services.
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        12,
        'Microsoft AZ-700 Azure Network Engineer Associate',
        'As an Azure Network Engineer, you plan, implement, and maintain Azure networking solutions, including hybrid networking, connectivity, routing, security, and private access to Azure services.',
        369,
        'https://examtopics.com/exams/microsoft/az-700/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-07'
    );

    -- Microsoft AZ-900 Azure Fundamentals
    -- Last updated on Jan. 9, 2026. questions 474
    -- This exam is intended for candidates looking to demonstrate foundational level knowledge of cloud services and how those services are provided with Microsoft Azure.
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        13,
        'Microsoft AZ-900 Azure Fundamentals',
        'This exam is intended for candidates looking to demonstrate foundational level knowledge of cloud services and how those services are provided with Microsoft Azure.',
        474,
        'https://examtopics.com/exams/microsoft/az-900/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-09'
    );


    -- Microsoft AZ-305  Azure Solutions Architect Expert
    -- Last updated on Dec. 20, 2025. questions 286
    -- As a Solutions Architect, you advise stakeholders and translate business requirements into secure, scalable, and reliable solutions.
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        14,
        'Microsoft AZ-305  Azure Solutions Architect Expert',
        'As a Solutions Architect, you advise stakeholders and translate business requirements into secure, scalable, and reliable solutions.',
        286,
        'https://examtopics.com/exams/microsoft/az-305/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2025-12-20'
    );


-- Microsoft DP-100 Designing and Implementing a Data Science Solution on Azure Last updated on Jan. 5, 2026. questions 527
-- learning workloads on Microsoft Azure using Azure Machine Learning service.

INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        15,
        'Microsoft DP-100 Designing and Implementing a Data Science Solution on Azure',
        'learning workloads on Microsoft Azure using Azure Machine Learning service.',
        527,
        'https://examtopics.com/exams/microsoft/dp-100/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-05'
    );

-- Microsoft DP-300 Administering Relational Databases on Microsoft Azure Last updated on Jan. 13, 2026. questions 373
-- Learn how to administer and manage cloud and on-premises relational databases built on top of Microsoft SQL Server and Microsoft Azure Data Services.

INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        16,
        'Microsoft DP-300 Administering Relational Databases on Microsoft Azure',
        'Learn how to administer and manage cloud and on-premises relational databases built on top of Microsoft SQL Server and Microsoft Azure Data Services.',
        373,
        'https://examtopics.com/exams/microsoft/dp-300/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-13'
    );

-- Microsoft DP-900 Azure Data Fundamentals Last updated on Jan. 4, 2026. questions 314
-- This exam is intended for candidates beginning to work with data in the cloud.
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        17,
        'Microsoft DP-900 Azure Data Fundamentals',
        'This exam is intended for candidates beginning to work with data in the cloud.',
        314,
        'https://examtopics.com/exams/microsoft/dp-900/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-04'
    );


    -- Databricks certified associate developer for apache spark
    

-- Databricks Certified Associate Developer for Apache Spark Actual Exam Questions
-- Last updated on Jan. 13, 2026. 342 questions
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        18,
        'Databricks Certified Associate Developer for Apache Spark',
        'Databricks Certified Associate Developer for Apache Spark Actual Exam Questions',
        342,
        'https://examtopics.com/exams/databricks/certified-associate-developer-for-apache-spark/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-13'
    );


    -- Databricks Certified Data Analyst Associate Actual Exam Questions
-- Last updated on Jan. 9, 2026. 85 questions
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        19,
        'Databricks Certified Data Analyst Associate',
        'as a Databricks Certified Data Analyst Associate, you demonstrate your knowledge of the Databricks Lakehouse Platform to perform basic data analysis tasks.',
        85,
        'https://examtopics.com/exams/databricks/certified-data-analyst-associate/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-09'
    );


    -- Databricks Certified Data Engineer Associate
-- Last updated on Jan. 14, 2026. 199 questions
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        20,
        'Databricks Certified Data Engineer Associate',
        'As a Databricks Certified Data Engineer Associate, you demonstrate your knowledge of the Databricks Lakehouse Platform to perform basic data engineering tasks.',
        199,
        'https://examtopics.com/exams/databricks/certified-data-engineer-associate/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-14'
    );

    -- Databricks Certified Generative AI Engineer Associate
-- Last updated on Jan. 7, 2026.

INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        21,
        'Databricks Certified Generative AI Engineer Associate',
        'As a Databricks Certified Generative AI Engineer Associate, you demonstrate your knowledge of the Databricks Lakehouse Platform to perform basic generative AI engineering tasks.',
        92,
        'https://www.examtopics.com/exams/databricks/certified-generative-ai-engineer-associate/view/',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        '2026-01-07'
    );



    -- Databricks Certified Machine Learning Associate
-- Last updated on Jan. 7, 2026. 140 questions
INSERT INTO
    projects (
        id,
        name,
        description,
        questions,
        link,
        created_at,
        updated_at,
        LastUpdatedOn
    )
VALUES (
        22,
        'Databricks Certified Machine Learning Associate',
        'As a Databricks Certified Machine Learning Associate, you demonstrate your knowledge of the Databricks Lakehouse Platform to perform basic machine learning tasks.',
        140,
        'https://examtopics.com/exams/databricks/certified-machine-learning-associate/view/',
        CURRENT_TIMESTAMP, 
        CURRENT_TIMESTAMP,
        '2026-01-07'
    );
