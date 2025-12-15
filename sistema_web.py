import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import locale
import matplotlib.pyplot as plt  # <--- A LINHA QUE FALTOU ESTÁ AQUI
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

# Configuração de Locale BR (Tenta ajustar para português)
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil.1252')
    except:
        pass

def formatar_br(valor, moeda=False):
    try:
        texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}" if moeda else texto
    except:
        return str(valor)

# --- PARSER XML (Lógica de leitura das notas) ---
class NFeParser:
    def __init__(self):
        self.ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

    def parse_files(self, xml_content):
        data_list = []
        errors = []
        try:
            # Remove caracteres estranhos do início se houver (BOM)
            xml_content = xml_content.strip()
            
            root = ET.fromstring(xml_content)
            emit = root.find('.//nfe:emit', self.ns)
            
            for item in root.findall('.//nfe:det', self.ns):
                prod = item.find('nfe:prod', self.ns)
                imposto = item.find('nfe:imposto', self.ns)

                codigo = prod.find('nfe:cProd', self.ns).text
                descricao = prod.find('nfe:xProd', self.ns).text
                ncm = prod.find('nfe:NCM', self.ns).text if prod.find('nfe:NCM', self.ns) is not None else ""
                
                qcom = float(prod.find('nfe:qCom', self.ns).text)
                vprod = float(prod.find('nfe:vProd', self.ns).text)

                vfrete = float(prod.find('nfe:vFrete', self.ns).text) if prod.find('nfe:vFrete', self.ns) is not None else 0.0
                vseg = float(prod.find('nfe:vSeg', self.ns).text) if prod.find('nfe:vSeg', self.ns) is not None else 0.0
                voutro = float(prod.find('nfe:vOutro', self.ns).text) if prod.find('nfe:vOutro', self.ns) is not None else 0.0

                vipi = 0.0
                vicms_st = 0.0

                if imposto is not None:
                    ipi_tag = imposto.find('.//nfe:IPI/nfe:IPITrib/nfe:vIPI', self.ns)
                    if ipi_tag is not None: vipi = float(ipi_tag.text)
                    for child in imposto.iter():
                        tag_name = child.tag.split('}')[-1]
                        if tag_name == 'vICMSST' and child.text:
                            vicms_st += float(child.text)

                custo_total_item = vprod + vfrete + vseg + voutro + vipi + vicms_st
                custo_unitario_final = custo_total_item / qcom if qcom > 0 else 0.0

                data_list.append({
                    'NCM': ncm,
                    'Código': codigo,
                    'Descrição': descricao,
                    'Custo Real Unit.': custo_unitario_final,
                    'Preço Praticado': 0.0
                })
        except Exception as e:
            errors.append(f"Erro ao ler XML: {str(e)}")
        return data_list, errors

# --- INTERFACE WEB (STREAMLIT) ---
st.set_page_config(page_title="Precificação Simples", layout="wide", initial_sidebar_state="expanded")

st.title("🛒 Gestão de Precificação - Simples Nacional")
st.markdown("---")

# Sidebar para configurações
st.sidebar.header("⚙️ Configurações")
simples = st.sidebar.slider("Alíquota Simples (%)", 1.0, 33.0, 4.0) / 100
despesas = st.sidebar.slider("Despesas Operacionais (%)", 5.0, 50.0, 15.0) / 100
lucro_meta = st.sidebar.slider("Margem de Lucro Meta (%)", 10.0, 100.0, 20.0) / 100

# Upload de XML
uploaded_files = st.file_uploader("📂 Importar XML(s) de Notas Fiscais", type=['xml'], accept_multiple_files=True)

# Inicializa o DataFrame na sessão se não existir
if 'df_produtos' not in st.session_state:
    st.session_state.df_produtos = pd.DataFrame()

# Processamento ao carregar arquivos
if uploaded_files:
    # Botão para processar (evita recarregar toda hora)
    if st.button("Processar Arquivos Carregados"):
        data_list = []
        for uploaded_file in uploaded_files:
            # Lê o arquivo como string
            stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
            xml_content = stringio.read()
            
            data, errors = NFeParser().parse_files(xml_content)
            data_list.extend(data)
            if errors:
                st.warning(f"⚠️ Aviso no arquivo {uploaded_file.name}: {errors}")
        
        if data_list:
            st.session_state.df_produtos = pd.DataFrame(data_list)
            st.success(f"✅ {len(data_list)} itens carregados com sucesso!")

# Se houver dados carregados, mostra a interface
if not st.session_state.df_produtos.empty:
    df = st.session_state.df_produtos
    
    # Cálculo do Preço Sugerido
    divisor = 1 - (simples + despesas + lucro_meta)
    if divisor > 0:
        df['Preço Sugerido'] = df['Custo Real Unit.'] / divisor
        # Preenche Preço Praticado com Sugerido se estiver zerado
        mask = df['Preço Praticado'] == 0
        df.loc[mask, 'Preço Praticado'] = df.loc[mask, 'Preço Sugerido']
    
    # --- ÁREA DE EDIÇÃO ---
    st.subheader("📋 Lista de Produtos (Edite o Preço de Venda)")
    
    # Usando o editor de dados nativo do Streamlit (Mais rápido e moderno)
    edited_df = st.data_editor(
        df,
        column_config={
            "Preço Praticado": st.column_config.NumberColumn(
                "Seu Preço de Venda (R$)",
                help="Digite quanto você cobra por este item",
                format="R$ %.2f",
                min_value=0.0,
            ),
            "Custo Real Unit.": st.column_config.NumberColumn(
                "Custo Real",
                format="R$ %.2f",
                disabled=True
            ),
            "Preço Sugerido": st.column_config.NumberColumn(
                "Sugerido",
                format="R$ %.2f",
                disabled=True
            ),
            "Descrição": st.column_config.TextColumn("Produto", disabled=True),
            "NCM": st.column_config.TextColumn("NCM", disabled=True),
            "Código": st.column_config.TextColumn("Cód.", disabled=True),
        },
        hide_index=True,
        use_container_width=True
    )
    
    # Atualiza o DataFrame com as edições
    st.session_state.df_produtos = edited_df

    st.markdown("---")

    # --- BOTÃO DE CÁLCULO FINAL ---
    if st.button("🚀 Calcular Lucratividade Real", type="primary"):
        # Realiza os cálculos finais baseados no DataFrame editado
        res_df = st.session_state.df_produtos.copy()
        
        res_df['V. Simples'] = res_df['Preço Praticado'] * simples
        res_df['V. Despesas'] = res_df['Preço Praticado'] * despesas
        res_df['Lucro R$'] = res_df['Preço Praticado'] - res_df['V. Simples'] - res_df['V. Despesas'] - res_df['Custo Real Unit.']
        res_df['Markup'] = res_df['Preço Praticado'] / res_df['Custo Real Unit.']
        
        # Dashboard
        st.subheader("📊 Resultados da Análise")
        
        # Métricas (KPIs)
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Faturamento Total", formatar_br(res_df['Preço Praticado'].sum(), True))
        kpi2.metric("Custo Total", formatar_br(res_df['Custo Real Unit.'].sum(), True))
        
        lucro_total = res_df['Lucro R$'].sum()
        kpi3.metric("Lucro Líquido Total", formatar_br(lucro_total, True), 
                   delta="Positivo" if lucro_total > 0 else "Prejuízo")
        
        margem_media = (lucro_total / res_df['Preço Praticado'].sum()) * 100 if res_df['Preço Praticado'].sum() > 0 else 0
        kpi4.metric("Margem Média Real", f"{margem_media:.1f}%")

        # Gráfico
        col_graf, col_tab = st.columns([1, 2])
        
        with col_graf:
            st.markdown("##### Para onde vai o dinheiro?")
            # Dados consolidados
            total_venda = res_df['Preço Praticado'].sum()
            total_custo = res_df['Custo Real Unit.'].sum()
            total_simples = res_df['V. Simples'].sum()
            total_despesas = res_df['V. Despesas'].sum()
            total_lucro = max(0, total_venda - total_custo - total_simples - total_despesas)
            
            sizes = [total_custo, total_simples, total_despesas, total_lucro]
            labels = ['Custo Mercadoria', 'Simples Nacional', 'Despesas Oper.', 'Lucro Líquido']
            colors = ['#95a5a6', '#f39c12', '#9b59b6', '#2ecc71']
            
            fig, ax = plt.subplots(figsize=(4, 4))
            ax.pie(sizes, labels=None, autopct='%1.1f%%', startangle=90, colors=colors, pctdistance=0.85)
            ax.legend(labels, loc="center", bbox_to_anchor=(0.5, -0.2))
            st.pyplot(fig)

        with col_tab:
            st.markdown("##### Detalhamento por Item")
            # Formata para exibição
            display_df = res_df[['Descrição', 'Custo Real Unit.', 'Preço Praticado', 'Lucro R$', 'Markup']].copy()
            st.dataframe(display_df.style.format({
                'Custo Real Unit.': 'R$ {:.2f}',
                'Preço Praticado': 'R$ {:.2f}',
                'Lucro R$': 'R$ {:.2f}',
                'Markup': '{:.2f}'
            }))

        # Download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            res_df.to_excel(writer, index=False)
        
        st.download_button(
            label="💾 Baixar Relatório Completo (Excel)",
            data=output.getvalue(),
            file_name="relatorio_lucratividade.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )